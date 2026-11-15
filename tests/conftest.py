"""Test helpers. Every test starts with an empty database (fictional data only)."""
import os
import tempfile
from datetime import date, timedelta

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["DEMO_MODE"] = "false"
os.environ["ADMIN_EMAILS"] = ""
os.environ["STORAGE_BACKEND"] = "database"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import FeeRule, User  # noqa: E402
from app.security import auth_limiter, hash_password  # noqa: E402
from app.seed import ensure_reference_data  # noqa: E402
from app.services import checks  # noqa: E402

API = "/api/v1"
HEADERS = {"X-Requested-With": "fetch"}
PASSWORD = "password-1234"
PDF = b"%PDF-1.4\n% test file\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    auth_limiter.reset()
    checks.reset_timer()
    db = SessionLocal()
    ensure_reference_data(db)
    db.close()
    yield


class Client(TestClient):
    """TestClient that prefixes /api/v1 and sends the CSRF header."""

    def __init__(self):
        super().__init__(app)
        self.headers.update(HEADERS)

    def call(self, method: str, path: str, expect: int | None = None, **kw):
        r = self.request(method, API + path, **kw)
        if expect is not None:
            assert r.status_code == expect, f"{method} {path} -> {r.status_code}: {r.text[:500]}"
        return r

    def ok(self, method: str, path: str, **kw):
        r = self.request(method, API + path, **kw)
        assert r.status_code < 300, f"{method} {path} -> {r.status_code}: {r.text[:500]}"
        return r.json() if r.status_code != 204 else None


def register(role: str, email: str, name: str = "Test Person", org_name: str = "Test Org") -> Client:
    c = Client()
    body = {"email": email, "password": PASSWORD, "name": name, "role": role, "accept_terms": True, "locale": "en"}
    if role == "organization":
        body["org_name"] = org_name
    c.ok("POST", "/auth/register", json=body)
    return c


def make_admin(email: str = "admin@example.com") -> Client:
    db = SessionLocal()
    db.add(User(email=email, password_hash=hash_password(PASSWORD), role="admin", name="Admin Person"))
    db.commit()
    db.close()
    c = Client()
    c.ok("POST", "/auth/login", json={"email": email, "password": PASSWORD})
    return c


def discipline_id(c: Client, code: str = "structural") -> int:
    return next(d["id"] for d in c.ok("GET", "/disciplines") if d["code"] == code)


def verify_org(owner: Client, admin: Client) -> None:
    owner.ok("PATCH", "/organizations/me", json={"cr_number": "1010-TEST", "city": "Riyadh",
                                                   "representative_name": "Rep Person"})
    owner.ok("POST", "/organizations/me/verification", files={"documents": ("cr.pdf", PDF, "application/pdf")},
             data={"note": "test"})
    vid = admin.ok("GET", "/admin/verifications")[0]["id"]
    admin.ok("POST", f"/admin/verifications/{vid}/decision", json={"decision": "approve", "note": ""})


def verify_engineer(eng: Client, admin: Client) -> None:
    eng.ok("PATCH", "/engineers/me", json={"title": "Structural Engineer", "discipline_id": discipline_id(eng),
                                           "years_experience": 7})
    eng.ok("POST", "/engineers/me/verification", files={"documents": ("degree.pdf", PDF, "application/pdf")})
    vid = next(v["id"] for v in admin.ok("GET", "/admin/verifications") if v["subject_type"] == "engineer")
    admin.ok("POST", f"/admin/verifications/{vid}/decision", json={"decision": "approve", "note": ""})


def future(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def add_fee_rules() -> None:
    db = SessionLocal()
    db.add(FeeRule(model="A", payer="both", fee_type="percent", org_value=250, engineer_value=500))
    db.add(FeeRule(model="B", payer="organization", fee_type="percent", org_value=800, engineer_value=0))
    db.commit()
    db.close()


@pytest.fixture
def world():
    """A verified organization (owner), two verified engineers and an administrator."""
    admin = make_admin()
    owner = register("organization", "owner@example.com", "Olivia Owner", "Example Consultants")
    eng = register("engineer", "eng@example.com", "Eddie Engineer")
    eng2 = register("engineer", "eng2@example.com", "Erin Engineer")
    verify_org(owner, admin)
    verify_engineer(eng, admin)
    verify_engineer(eng2, admin)
    add_fee_rules()
    return {"admin": admin, "owner": owner, "eng": eng, "eng2": eng2}


def invite_member(owner: Client, email: str, role: str, name: str = "Team Member") -> Client:
    link = owner.ok("POST", "/organizations/me/invitations", json={"email": email, "name": name, "org_role": role})["link"]
    token = link.rsplit("/", 1)[-1]
    c = Client()
    c.ok("POST", "/auth/invitations/accept", json={"token": token, "name": name, "password": PASSWORD})
    return c


def new_project(owner: Client, **over) -> dict:
    body = {"title": "Structural design of a warehouse", "description": "Steel portal frame warehouse design, 40 x 60 m.",
            "discipline_id": discipline_id(owner), "scope": "Design and drawings", "deliverables_text": "Report; drawings",
            "work_mode": "remote", "location": "", "budget_min_cents": 100000, "max_budget_cents": 500000,
            "duration_days": 30, "proposal_deadline": future(10), "deadline": future(60)} | over
    return owner.ok("POST", "/projects", json=body)


def proposal_body(price: int = 400000) -> dict:
    return {"price_cents": price, "delivery_date": future(40), "duration_days": 30,
            "message": "I have designed many steel warehouses.", "technical_approach": "Model in ETABS, check per SBC, issue drawings."}
