"""Sign-up, log-in, log-out, own account, password change, invitations, and (demo mode only) one-click demo logins."""
import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import schemas as s
from app.config import get_settings
from app.database import get_db
from app.errors import ApiError, bad_request, conflict, not_found
from app.models import EngineerProfile, Organization, OrgInvitation, OrgMember, OrgRole, Role, User
from app.security import (
    auth_limiter,
    clear_session_cookie,
    client_ip,
    create_session_cookie,
    current_user,
    dummy_verify,
    hash_password,
    verify_password,
)
from app.services import audit
from app.services.serialize import me_out

router = APIRouter(prefix="/auth", tags=["auth"])
TAKEN = ("An account with this e-mail already exists. Try logging in instead.",
         "يوجد حساب بهذا البريد الإلكتروني. جرّب تسجيل الدخول.")


@router.post("/register", status_code=201)
def register(body: s.RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    key = "register:" + client_ip(request)
    auth_limiter.check(key)
    auth_limiter.hit(key)
    email = body.email.lower()
    if email.endswith("@bunyah.test"):  # reserved for the fictional demo accounts
        raise bad_request("This e-mail domain is reserved for demo accounts.", "هذا النطاق مخصص للحسابات التجريبية.")
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise conflict(*TAKEN)
    if body.role == Role.ORGANIZATION and len(body.org_name) < 2:
        raise ApiError(422, "VALIDATION_ERROR", "Please enter the organization name.", "يرجى إدخال اسم الجهة.",
                       [{"field": "org_name", "issue": "Required for organizations"}])
    user = User(email=email, password_hash=hash_password(body.password), role=body.role, name=body.name,
                locale=body.locale, last_login_at=datetime.now(UTC))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise conflict(*TAKEN)
    if body.role == Role.ORGANIZATION:
        org = Organization(name=body.org_name, representative_name=body.name)
        db.add(org)
        db.flush()
        db.add(OrgMember(org_id=org.id, user_id=user.id, org_role=OrgRole.OWNER))
    else:
        db.add(EngineerProfile(user_id=user.id))
    audit.record(db, user, "account.registered", "user", user.id, ip=client_ip(request), role=body.role)
    db.commit()
    create_session_cookie(response, user)
    return me_out(db, user)


@router.post("/login")
def login(body: s.LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    key = "login:" + client_ip(request)
    auth_limiter.check(key)
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None:
        dummy_verify()
    if user is None or not verify_password(body.password, user.password_hash):
        auth_limiter.hit(key)
        raise ApiError(401, "INVALID_LOGIN", "That e-mail and password don't match. Please try again.",
                       "البريد الإلكتروني وكلمة المرور غير متطابقين. حاول مرة أخرى.")
    if not user.is_active:
        raise ApiError(403, "ACCOUNT_SUSPENDED", "This account is suspended. Contact the BUNYAH team.",
                       "هذا الحساب موقوف. تواصل مع فريق بُنية.")
    user.last_login_at = datetime.now(UTC)
    db.commit()
    create_session_cookie(response, user)
    return me_out(db, user)


@router.post("/logout", status_code=204)
def logout(response: Response):
    clear_session_cookie(response)
    response.status_code = 204
    return response


@router.get("/me")
def me(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return me_out(db, user)


@router.patch("/me")
def update_me(body: s.AccountUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(user, k, v)
    db.commit()
    return me_out(db, user)


@router.post("/password", status_code=204)
def change_password(body: s.PasswordChangeIn, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    key = "password:" + str(user.id)
    auth_limiter.check(key)
    if not verify_password(body.current_password, user.password_hash):
        auth_limiter.hit(key)
        raise bad_request("Your current password is not correct.", "كلمة المرور الحالية غير صحيحة.", "WRONG_PASSWORD")
    user.password_hash = hash_password(body.new_password)
    audit.record(db, user, "account.password_changed", "user", user.id, ip=client_ip(request))
    db.commit()
    return Response(status_code=204)


# ---------- invitations (organization team members) ----------
def _invite_by_token(db: Session, token: str) -> OrgInvitation:
    inv = db.scalar(select(OrgInvitation).where(OrgInvitation.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    if inv is None or inv.accepted_at or inv.revoked_at or inv.expires_at < datetime.now(UTC):
        raise not_found("Invitation", "الدعوة")
    return inv


@router.get("/invitations/{token}")
def invitation_preview(token: str, db: Session = Depends(get_db)):
    inv = _invite_by_token(db, token)
    org = db.get(Organization, inv.org_id)
    return {"organization": org.name, "email": inv.email, "name": inv.name, "org_role": inv.org_role}


@router.post("/invitations/accept", status_code=201)
def accept_invitation(body: s.AcceptInviteIn, request: Request, response: Response, db: Session = Depends(get_db)):
    key = "invite:" + client_ip(request)
    auth_limiter.check(key)
    auth_limiter.hit(key)
    inv = _invite_by_token(db, body.token)
    if db.scalar(select(User.id).where(func.lower(User.email) == inv.email.lower())):
        raise conflict(*TAKEN)
    user = User(email=inv.email.lower(), password_hash=hash_password(body.password), role=Role.ORGANIZATION,
                name=body.name, last_login_at=datetime.now(UTC))
    db.add(user)
    db.flush()
    db.add(OrgMember(org_id=inv.org_id, user_id=user.id, org_role=inv.org_role))
    inv.accepted_at = datetime.now(UTC)
    audit.record(db, user, "team.invitation_accepted", "organization", inv.org_id, role=inv.org_role)
    db.commit()
    create_session_cookie(response, user)
    return me_out(db, user)


# ---------- demo mode ----------
def _demo_only() -> None:
    if not get_settings().demo_mode:
        raise not_found("Page", "الصفحة")


@router.get("/demo-accounts")
def demo_accounts(db: Session = Depends(get_db)):
    """Fictional demo accounts (demo mode only) so the prototype can be tested without typing passwords."""
    _demo_only()
    from app.seed import DEMO_ACCOUNTS
    out = []
    for key, acc in DEMO_ACCOUNTS.items():
        if db.scalar(select(User.id).where(User.email == acc["email"])):
            out.append({"key": key, "label_en": acc["label_en"], "label_ar": acc["label_ar"], "email": acc["email"],
                        "group": acc["group"]})
    return out


@router.post("/demo-login")
def demo_login(body: s.DemoLoginIn, response: Response, db: Session = Depends(get_db)):
    _demo_only()
    from app.seed import DEMO_ACCOUNTS
    acc = DEMO_ACCOUNTS.get(body.key)
    user = db.scalar(select(User).where(User.email == acc["email"])) if acc else None
    if user is None or not user.is_active:
        raise not_found("Demo account", "الحساب التجريبي")
    user.last_login_at = datetime.now(UTC)
    db.commit()
    create_session_cookie(response, user)
    return me_out(db, user)
