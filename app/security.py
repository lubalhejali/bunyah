"""Passwords, login cookies, "who is logged in", role-based permissions and rate limiting."""
import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.errors import ApiError, forbidden
from app.models import Organization, OrgMember, OrgRole, Role, User

COOKIE_NAME = "bunyah_session"

# ---------- passwords (scrypt, built into Python) ----------
_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(_N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt_b64, digest_b64 = stored.split("$")
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(digest_b64)
        actual = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = hash_password(secrets.token_hex(16))


def dummy_verify() -> None:
    """Makes 'unknown e-mail' take as long as 'wrong password', so attackers can't probe e-mails."""
    verify_password("not-the-password", _DUMMY_HASH)


# ---------- login cookie (signed token) ----------
def create_session_cookie(response: Response, user: User) -> None:
    s = get_settings()
    now = datetime.now(UTC)
    token = jwt.encode({"sub": str(user.id), "iat": now, "exp": now + timedelta(hours=s.session_hours)},
                       s.secret_key, algorithm="HS256")
    response.set_cookie(COOKIE_NAME, token, max_age=s.session_hours * 3600, httponly=True,
                        secure=s.is_production, samesite="lax", path="/")


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def _user_from_request(request: Request, db: Session) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:  # suspended accounts are logged out immediately
        return None
    return user


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = _user_from_request(request, db)
    if user is None:
        raise ApiError(401, "UNAUTHORIZED", "Please log in to continue.", "يرجى تسجيل الدخول للمتابعة.")
    return user


def is_admin(user: User) -> bool:
    return user.role == Role.ADMIN or user.email.lower() in get_settings().admin_email_set


def admin_ids(db: Session) -> list[int]:
    emails = get_settings().admin_email_set
    cond = User.role == Role.ADMIN
    if emails:
        cond = or_(cond, func.lower(User.email).in_(emails))
    return list(db.scalars(select(User.id).where(cond, User.is_active.is_(True))).all())


def require_admin(user: User = Depends(current_user)) -> User:
    if not is_admin(user):
        raise forbidden("Administrators only.", "هذه الصفحة للإدارة فقط.")
    return user


def require_engineer(user: User = Depends(current_user)) -> User:
    if user.role != Role.ENGINEER:
        raise forbidden("Only engineer accounts can do this.", "هذا الإجراء متاح لحسابات المهندسين فقط.")
    return user


# ---------- organization roles ----------
PERMISSIONS: dict[str, tuple[str, ...]] = {
    "org.edit": (OrgRole.OWNER,),
    "team.manage": (OrgRole.OWNER,),
    "work.manage": (OrgRole.OWNER, OrgRole.PROJECT_MANAGER),          # publish, evaluate, select, manage work
    "work.review": (OrgRole.OWNER, OrgRole.PROJECT_MANAGER, OrgRole.TECHNICAL_REVIEWER),  # review deliverables
    "contract.sign": (OrgRole.OWNER,),                                 # signs on behalf of the organization
    "billing.approve": (OrgRole.OWNER, OrgRole.PROJECT_MANAGER),
    "finance.view": (OrgRole.OWNER, OrgRole.PROJECT_MANAGER, OrgRole.FINANCE),
    "finance.pay": (OrgRole.OWNER, OrgRole.FINANCE),
    "messages.send": (OrgRole.OWNER, OrgRole.PROJECT_MANAGER, OrgRole.TECHNICAL_REVIEWER),
    "dispute.raise": (OrgRole.OWNER, OrgRole.PROJECT_MANAGER),
    "view": OrgRole.ALL,
}


@dataclass
class OrgContext:
    user: User
    member: OrgMember
    org: Organization

    def can(self, perm: str) -> bool:
        return self.member.org_role in PERMISSIONS[perm]

    def require(self, perm: str) -> None:
        if not self.can(perm):
            raise forbidden("Your role in this organization doesn't allow this action.",
                            "دورك في هذه الجهة لا يسمح بهذا الإجراء.")


def org_context(db: Session, user: User) -> OrgContext | None:
    if user.role != Role.ORGANIZATION:
        return None
    m = db.scalar(select(OrgMember).where(OrgMember.user_id == user.id, OrgMember.is_active.is_(True)))
    if m is None:
        return None
    return OrgContext(user=user, member=m, org=db.get(Organization, m.org_id))


def require_org(user: User = Depends(current_user), db: Session = Depends(get_db)) -> OrgContext:
    ctx = org_context(db, user)
    if ctx is None:
        raise forbidden("Only organization accounts can do this.", "هذا الإجراء متاح لحسابات الجهات فقط.")
    return ctx


def permissions_for(role: str) -> list[str]:
    return [p for p, roles in PERMISSIONS.items() if role in roles]


# ---------- tiny in-memory rate limiter (per IP) ----------
class RateLimiter:
    def __init__(self, max_hits: int, per_seconds: int):
        self.max_hits, self.per = max_hits, per_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.per:
                q.popleft()
            if not q:
                self._hits.pop(key, None)
            elif len(q) >= self.max_hits:
                raise ApiError(429, "RATE_LIMITED", "Too many attempts. Please wait a few minutes and try again.",
                               "محاولات كثيرة. يرجى الانتظار بضع دقائق ثم المحاولة مرة أخرى.")

    def hit(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(time.monotonic())

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


auth_limiter = RateLimiter(max_hits=10, per_seconds=300)


def client_ip(request: Request) -> str:
    # Correct on Render only because the start command passes --proxy-headers (see render.yaml).
    return request.client.host if request.client else "unknown"
