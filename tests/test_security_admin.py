"""Scenario D (administrator) plus security checks: access control, private files, uploads, CSRF, audit."""
from datetime import date

from app.services.calendar import WorkCalendar
from app.services.finance import compute_fees
from app.models import FeeRule
from tests.conftest import PDF, PNG, Client, make_admin, new_project, register
from tests.test_model_a import _to_in_progress


def test_admin_scenario(world):
    admin, owner = world["admin"], world["owner"]
    # 1-2: review verification requests, approve or reject
    o2 = register("organization", "o2@example.com", "Second Owner", "Second Org")
    o2.call("POST", "/organizations/me/verification", 400, files={"documents": ("cr.pdf", PDF)})  # profile incomplete
    o2.ok("PATCH", "/organizations/me", json={"cr_number": "123", "city": "Jeddah", "representative_name": "Rep"})
    o2.ok("POST", "/organizations/me/verification", files={"documents": ("cr.pdf", PDF)})
    o2.call("POST", "/organizations/me/verification", 409, files={"documents": ("cr.pdf", PDF)})  # already pending
    pending = admin.ok("GET", "/admin/verifications")
    assert len(pending) == 1
    detail = admin.ok("GET", f"/admin/verifications/{pending[0]['id']}")
    assert detail["subject"]["cr_number"] == "123" and detail["documents"]
    admin.call("POST", f"/admin/verifications/{pending[0]['id']}/decision", 400, json={"decision": "reject", "note": ""})
    admin.ok("POST", f"/admin/verifications/{pending[0]['id']}/decision", json={"decision": "reject", "note": "CR unreadable"})
    assert o2.ok("GET", "/organizations/me")["verification_status"] == "rejected"
    # 3: monitor projects and contracts
    _to_in_progress(world)
    assert admin.ok("GET", "/admin/projects")[0]["status"] == "in_progress"
    admin.ok("GET", "/admin/contracts")
    admin.ok("GET", "/admin/proposals")
    # 5: adjust configurable fees (audited, old invoices keep their snapshot)
    admin.ok("POST", "/admin/fee-rules", json={"model": "A", "payer": "organization", "fee_type": "fixed",
                                               "org_value": 5000, "engineer_value": 0, "note": "test"})
    rules = admin.ok("GET", "/admin/fee-rules")
    assert sum(r["is_active"] for r in rules if r["model"] == "A") == 1
    admin.call("POST", "/admin/fee-rules", 400, json={"model": "A", "payer": "both", "fee_type": "percent",
                                                      "org_value": 6000, "engineer_value": 0})
    # 6: analytics and audit log
    ov = admin.ok("GET", "/admin/overview")
    assert ov["projects_by_status"]["in_progress"] == 1
    actions = {x["action"] for x in admin.ok("GET", "/admin/audit-logs")["data"]}
    assert {"verification.reject", "finance.fee_rule_changed", "verification.approve"} <= actions
    # user management: suspend logs the person out immediately
    uid = owner.ok("GET", "/auth/me")["id"]
    admin.ok("PATCH", f"/admin/users/{uid}", json={"is_active": False})
    owner.call("GET", "/auth/me", 401)
    admin.ok("PATCH", f"/admin/users/{uid}", json={"is_active": True})
    me = admin.ok("GET", "/auth/me")["id"]
    admin.call("PATCH", f"/admin/users/{me}", 409, json={"is_active": False})
    # disciplines, holidays, announcements
    admin.ok("POST", "/admin/disciplines", json={"code": "fire_safety", "name_en": "Fire Safety", "name_ar": "السلامة من الحريق"})
    admin.ok("POST", "/admin/holidays", json={"day": "2027-12-01", "name_en": "National Day", "name_ar": "اليوم الوطني"})
    assert admin.ok("POST", "/admin/announcements", json={"audience": "engineer", "text": "Welcome to the pilot"})["recipients"] == 2


def test_non_admins_are_refused(world):
    for c in (world["owner"], world["eng"]):
        for path in ("/admin/overview", "/admin/users", "/admin/settings", "/admin/audit-logs", "/admin/finance"):
            c.call("GET", path, 403)
    Client().call("GET", "/admin/overview", 401)


def test_private_files_and_upload_checks(world):
    owner, eng, eng2 = world["owner"], world["eng"], world["eng2"]
    p, _ = _to_in_progress(world)
    d = owner.ok("POST", f"/projects/{p['id']}/deliverables", json={"title": "Report"})
    eng.ok("POST", f"/deliverables/{d['id']}/versions", files={"file": ("r.pdf", PDF)})
    fid = owner.ok("GET", f"/projects/{p['id']}/deliverables")[0]["versions"][0]["file"]["id"]
    r = owner.call("GET", f"/files/{fid}")
    assert r.status_code == 200 and r.headers["content-disposition"].startswith("attachment")
    assert "sandbox" in r.headers["content-security-policy"]
    eng2.call("GET", f"/files/{fid}", 404)                                      # other engineers can't download
    # verification documents are never public
    other_org = register("organization", "oo@example.com", "Other Owner", "Other Org")
    vdoc = next(f for v in eng.ok("GET", "/verification/mine") for f in v["documents"])
    other_org.call("GET", f"/files/{vdoc['id']}", 404)
    eng2.call("GET", f"/files/{vdoc['id']}", 404)
    assert world["admin"].call("GET", f"/files/{vdoc['id']}").status_code == 200
    # renamed executables and wrong formats are refused
    eng.call("POST", f"/deliverables/{d['id']}/versions", 400, files={"file": ("tool.exe", b"MZ\x90")})
    eng.call("POST", f"/deliverables/{d['id']}/versions", 400, files={"file": ("fake.pdf", b"MZ\x90\x00 not a pdf")})
    eng.call("POST", f"/deliverables/{d['id']}/versions", 400, files={"file": ("drawing.dwg", b"not a dwg file")})
    eng.call("POST", f"/deliverables/{d['id']}/versions", 400, files={"file": ("empty.pdf", b"")})
    eng.ok("POST", f"/deliverables/{d['id']}/versions", files={"file": ("plan.dwg", b"AC1032" + b"\x00" * 20)})
    owner.ok("POST", "/organizations/me/logo", files={"file": ("logo.png", PNG)})
    owner.call("POST", "/organizations/me/logo", 400, files={"file": ("logo.pdf", PDF)})


def test_csrf_headers_and_mass_assignment():
    c = Client()
    c.headers.pop("X-Requested-With")
    r = c.call("POST", "/auth/login", 403, json={"email": "a@b.co", "password": "x"})
    assert r.json()["error"]["code"] == "CSRF"
    r = Client().call("GET", "/auth/me", 401)
    h = r.headers
    assert h["x-frame-options"] == "DENY" and "default-src 'self'" in h["content-security-policy"]
    owner = register("organization", "mass@example.com", "Mass Owner", "Mass Org")
    owner.call("PATCH", "/organizations/me", 422, json={"verification_status": "verified"})
    eng = register("engineer", "mass-eng@example.com")
    eng.call("PATCH", "/engineers/me", 422, json={"verification_status": "verified"})
    Client().call("POST", "/auth/register", 422, json={"email": "x@bunyah.test", "password": "longpassword1", "name": "X Y",
                                                       "role": "engineer", "accept_terms": True})
    Client().call("POST", "/auth/register", 422, json={"email": "y@example.com", "password": "longpassword1", "name": "X Y",
                                                       "role": "admin", "accept_terms": True})
    Client().call("POST", "/auth/register", 422, json={"email": "z@example.com", "password": "longpassword1", "name": "X Y",
                                                       "role": "engineer", "accept_terms": False})


def test_demo_accounts_can_log_in_with_password_in_demo_seed():
    from app.database import SessionLocal
    from app.seed import DEMO_PASSWORD, seed_demo
    db = SessionLocal()
    assert seed_demo(db) is True and seed_demo(db) is False          # idempotent
    db.close()
    c = Client()
    me = c.ok("POST", "/auth/login", json={"email": "rawabi.owner@bunyah.test", "password": DEMO_PASSWORD})
    assert me["org_role"] == "owner" and me["organization"]["verification_status"] == "verified"
    assert c.ok("GET", "/dashboard")["role"] == "organization"


def test_login_rate_limit_and_demo_login_off():
    c = Client()
    for _ in range(10):
        c.call("POST", "/auth/login", 401, json={"email": "nobody@example.com", "password": "wrong"})
    c.call("POST", "/auth/login", 429, json={"email": "nobody@example.com", "password": "wrong"})
    Client().call("GET", "/auth/demo-accounts", 404)                           # DEMO_MODE is off in tests
    Client().call("POST", "/auth/demo-login", 404, json={"key": "admin"})


def test_legacy_payment_endpoints_are_switched_off():
    c = make_admin()
    for method, path in [("POST", "/projects/1/payment"), ("GET", "/wallet"), ("GET", "/admin/escrow")]:
        r = c.call(method, path, 410)
        assert r.json()["error"]["code"] == "FEATURE_SWITCHED_OFF"


def test_public_profile_hides_private_fields(world):
    eng_id = world["eng"].ok("GET", "/auth/me")["id"]
    world["eng"].ok("PATCH", "/engineers/me", json={"registration_number": "SCE-999"})
    pub = world["owner"].ok("GET", f"/engineers/{eng_id}")
    assert "registration_number" not in pub and "email" not in pub and "phone" not in pub
    org_id = world["owner"].ok("GET", "/organizations/me")["id"]
    pub_org = world["eng"].ok("GET", f"/organizations/{org_id}")
    assert "contact_email" not in pub_org and "cr_number" not in pub_org
    # changing registration details resets verification
    assert world["eng"].ok("GET", "/engineers/me")["verification_status"] == "unverified"


def test_team_invitation_flow(world):
    owner = world["owner"]
    eng = world["eng"]
    eng.call("POST", "/organizations/me/invitations", 403, json={"email": "x@example.com", "org_role": "viewer"})
    link = owner.ok("POST", "/organizations/me/invitations", json={"email": "pm2@example.com", "org_role": "project_manager"})["link"]
    token = link.rsplit("/", 1)[-1]
    assert Client().ok("GET", f"/auth/invitations/{token}")["org_role"] == "project_manager"
    c = Client()
    me = c.ok("POST", "/auth/invitations/accept", json={"token": token, "name": "New PM", "password": "password-1234"})
    assert me["org_role"] == "project_manager"
    Client().call("POST", "/auth/invitations/accept", 404, json={"token": token, "name": "Again", "password": "password-1234"})


def test_calendar_and_fee_math():
    cal = WorkCalendar({date(2026, 11, 17)})                               # a Tuesday holiday
    assert not cal.is_working_day(date(2026, 11, 20))                      # Friday
    assert not cal.is_working_day(date(2026, 11, 21))                      # Saturday
    assert cal.is_working_day(date(2026, 11, 22))                          # Sunday
    assert cal.add_working_days(date(2026, 11, 15), 5) == date(2026, 11, 23)  # skips Tue holiday + weekend
    periods = cal.split_periods(date(2026, 11, 15), 90, 20)
    assert [n for _, _, n in periods] == [20, 20, 20, 20, 10]
    assert cal.working_days_between(periods[0][0], periods[-1][1]) == 90
    assert [n for _, _, n in cal.split_periods(date(2026, 11, 15), 45, 20)] == [20, 20, 5]
    rule = FeeRule(id=1, model="A", payer="both", fee_type="percent", org_value=250, engineer_value=500)
    f = compute_fees(rule, 100000)
    assert f["org_fee_cents"] == 2500 and f["engineer_fee_cents"] == 5000
    fixed = FeeRule(id=2, model="B", payer="engineer", fee_type="fixed", org_value=0, engineer_value=200000)
    assert compute_fees(fixed, 100000)["engineer_fee_cents"] == 100000          # never more than the amount
    assert compute_fees(None, 100000)["org_fee_cents"] == 0


def test_project_visibility_rules(world):
    owner, eng = world["owner"], world["eng"]
    p = new_project(owner)
    eng.call("GET", f"/projects/{p['id']}", 404)
    owner.ok("POST", f"/projects/{p['id']}/publish")
    eng.ok("GET", f"/projects/{p['id']}")
    eng.call("GET", f"/projects/{p['id']}/events", 403)
    owner.ok("POST", f"/projects/{p['id']}/transitions", json={"to": "applications_closed"})
    eng.call("GET", f"/projects/{p['id']}", 404)                            # no longer public, no proposal
