"""Scenario C: the Model B short-term service contract workflow (demo data only)."""
from datetime import date, timedelta

from app.database import SessionLocal
from app.models import BillingPeriod, ServiceContract, ServiceRequest
from app.services.calendar import WorkCalendar
from tests.conftest import discipline_id, future


def request_body(c, **over):
    return {"title": "BIM Specialist for a hospital", "discipline_id": discipline_id(c, "bim"), "specialization": "Revit",
            "duration_working_days": 90, "hours_per_day": 8, "daily_rate_cents": 120000, "work_mode": "remote",
            "location": "", "start_date": future(3), "responsibilities": "Coordinate models and produce clash reports.",
            "outputs": "Weekly clash report"} | over


def _active_contract(w):
    owner, eng, admin = w["owner"], w["eng"], w["admin"]
    r = owner.ok("POST", "/service-requests", json=request_body(owner))
    owner.ok("POST", f"/service-requests/{r['id']}/submit")
    admin.ok("POST", f"/admin/service-requests/{r['id']}/review", json={"decision": "publish", "note": ""})
    owner.ok("POST", f"/service-requests/{r['id']}/transitions", json={"to": "applications_open"})
    ap = eng.ok("POST", f"/service-requests/{r['id']}/applications",
                json={"cover_letter": "Six years of BIM coordination work.", "proposed_daily_rate_cents": 110000,
                      "available_from": future(3)})
    owner.ok("POST", f"/service-requests/{r['id']}/transitions", json={"to": "under_evaluation"})
    owner.ok("POST", f"/applications/{ap['id']}/decision", json={"decision": "select", "note": ""})
    owner.ok("POST", f"/service-requests/{r['id']}/contract")
    owner.ok("POST", f"/service-requests/{r['id']}/contract/send")
    owner.ok("POST", f"/service-requests/{r['id']}/contract/sign", json={"full_name": "Olivia Owner", "confirm": True})
    eng.ok("POST", f"/service-requests/{r['id']}/contract/sign", json={"full_name": "Eddie Engineer", "confirm": True})
    return r


def _backdate(request_id: int, working_days_ago: int) -> None:
    """Moves an active contract's start into the past so work days can be recorded in a test."""
    db = SessionLocal()
    cal = WorkCalendar.load(db)
    c = db.query(ServiceContract).filter_by(request_id=request_id).one()
    start = date.today()
    for _ in range(working_days_ago):
        start -= timedelta(days=1)
        while not cal.is_working_day(start):
            start -= timedelta(days=1)
    for p in list(c.periods):
        db.delete(p)
    db.flush()
    c.start_date, c.end_date = start, cal.nth_working_day(start, c.working_days)
    for i, (s, e, n) in enumerate(cal.split_periods(start, c.working_days, c.period_length_days), start=1):
        db.add(BillingPeriod(contract_id=c.id, seq=i, start_date=s, end_date=e, working_days=n))
    db.commit()
    db.close()


def test_short_term_contract_end_to_end(world):
    owner, eng, eng2, admin = world["owner"], world["eng"], world["eng2"], world["admin"]
    # 1: publish a temporary engineering service request (with BUNYAH review)
    r = owner.ok("POST", "/service-requests", json=request_body(owner))
    assert r["status"] == "draft"
    owner.call("POST", "/service-requests", 400, json=request_body(owner, duration_working_days=91))  # over the 90-day setting
    assert owner.ok("POST", f"/service-requests/{r['id']}/submit")["status"] == "submitted"
    owner.call("POST", f"/service-requests/{r['id']}/transitions", 409, json={"to": "applications_open"})
    admin.ok("POST", f"/admin/service-requests/{r['id']}/review", json={"decision": "start", "note": ""})
    admin.call("POST", f"/admin/service-requests/{r['id']}/review", 400, json={"decision": "return", "note": ""})
    admin.ok("POST", f"/admin/service-requests/{r['id']}/review", json={"decision": "publish", "note": "OK"})
    owner.ok("POST", f"/service-requests/{r['id']}/transitions", json={"to": "applications_open"})

    # 2: engineers apply
    body = {"cover_letter": "I have coordinated hospital BIM models.", "proposed_daily_rate_cents": 110000, "available_from": future(3)}
    a1 = eng.ok("POST", f"/service-requests/{r['id']}/applications", json=body)
    eng2.ok("POST", f"/service-requests/{r['id']}/applications", json=body | {"proposed_daily_rate_cents": 130000})
    eng.call("POST", f"/service-requests/{r['id']}/applications", 409, json=body)   # only once

    # 3: compare and select
    assert len(owner.ok("GET", f"/service-requests/{r['id']}/applications")) == 2
    owner.call("POST", f"/applications/{a1['id']}/decision", 409, json={"decision": "select", "note": ""})  # still open
    owner.ok("POST", f"/service-requests/{r['id']}/transitions", json={"to": "under_evaluation"})
    assert owner.ok("POST", f"/applications/{a1['id']}/decision", json={"decision": "select", "note": ""})["status"] == "selected"

    # 4: contract preparation and simulated signatures
    rq = owner.ok("POST", f"/service-requests/{r['id']}/contract")
    assert rq["status"] == "contract_preparation" and rq["contract"]["daily_rate_cents"] == 110000
    owner.call("PATCH", f"/service-requests/{r['id']}/contract", 400, json={"working_days": 95})
    owner.ok("PATCH", f"/service-requests/{r['id']}/contract", json={"working_days": 90})
    owner.ok("POST", f"/service-requests/{r['id']}/contract/send")
    owner.call("POST", f"/service-requests/{r['id']}/contract/sign", 400, json={"full_name": "Someone Else", "confirm": True})
    owner.ok("POST", f"/service-requests/{r['id']}/contract/sign", json={"full_name": "olivia owner", "confirm": True})
    eng2.call("POST", f"/service-requests/{r['id']}/contract/sign", 403, json={"full_name": "Erin Engineer", "confirm": True})
    rq = eng.ok("POST", f"/service-requests/{r['id']}/contract/sign", json={"full_name": "Eddie Engineer", "confirm": True})
    assert rq["status"] == "active"
    # 90 working days -> 20 + 20 + 20 + 20 + 10
    assert [p["working_days"] for p in rq["contract"]["periods"]] == [20, 20, 20, 20, 10]

    # 5: daily work entries
    _backdate(r["id"], 3)
    db = SessionLocal()
    c = db.query(ServiceContract).filter_by(request_id=r["id"]).one()
    cal = WorkCalendar.load(db)
    days = [d for d in (c.start_date + timedelta(days=i) for i in range(6)) if cal.is_working_day(d) and d < date.today()]
    weekend = next(c.start_date + timedelta(days=i) for i in range(7) if not cal.is_working_day(c.start_date + timedelta(days=i)))
    db.close()
    entry = {"work_date": days[0].isoformat(), "day_fraction": 1.0, "hours": 8, "description": "Clash detection run"}
    eng.ok("POST", f"/service-requests/{r['id']}/time-entries", json=entry)
    eng.call("POST", f"/service-requests/{r['id']}/time-entries", 409, json=entry)              # same day twice
    eng.call("POST", f"/service-requests/{r['id']}/time-entries", 400, json=entry | {"work_date": weekend.isoformat()})
    eng.call("POST", f"/service-requests/{r['id']}/time-entries", 400, json=entry | {"work_date": future(1)})
    eng.call("POST", f"/service-requests/{r['id']}/time-entries", 400, json=entry | {"work_date": days[1].isoformat(), "day_fraction": 0.3})
    eng.ok("POST", f"/service-requests/{r['id']}/time-entries", json=entry | {"work_date": days[1].isoformat(), "day_fraction": 0.5})
    owner.call("POST", f"/service-requests/{r['id']}/time-entries", 403, json=entry | {"work_date": days[2].isoformat()})

    # 6: billing period review and approval
    period = eng.ok("GET", f"/service-requests/{r['id']}")["contract"]["periods"][0]
    owner.call("POST", f"/billing-periods/{period['id']}/review", 409, json={"decision": "approve"})  # not submitted
    eng.ok("POST", f"/billing-periods/{period['id']}/submit")
    eng.call("POST", f"/service-requests/{r['id']}/time-entries", 409, json=entry | {"work_date": days[2].isoformat()})  # locked
    owner.ok("POST", f"/billing-periods/{period['id']}/review", json={"decision": "revision", "comment": "Add detail to day 2"})
    eng.ok("POST", f"/billing-periods/{period['id']}/submit")
    rq = owner.ok("POST", f"/billing-periods/{period['id']}/review", json={"decision": "approve", "comment": ""})
    p1 = rq["contract"]["periods"][0]
    assert p1["status"] == "approved" and p1["approved_days"] == 1.5 and p1["amount_cents"] == 165000  # 1.5 x 1,100 SAR

    # 7: both parties see the simulated financial summary
    fo = owner.ok("GET", f"/service-requests/{r['id']}/finance")
    fe = eng.ok("GET", f"/service-requests/{r['id']}/finance")
    assert fo["simulated"] and fo["invoiced_cents"] == 165000 == fe["invoiced_cents"]
    inv = fo["invoices"][0]
    assert inv["org_fee_cents"] == 13200 and inv["engineer_fee_cents"] == 0     # Model B demo rule: org pays 8%
    owner.ok("POST", f"/invoices/{inv['id']}/pay")
    assert eng.ok("GET", "/finance")["totals"]["payouts_pending_cents"] == 165000

    # Ending: completion needs every period with days approved; early termination needs a reason
    eng.call("POST", f"/service-requests/{r['id']}/finish", 400, json={"outcome": "terminated", "reason": ""})
    assert owner.ok("POST", f"/service-requests/{r['id']}/finish", json={"outcome": "completed"})["status"] == "completed"
    owner.ok("POST", f"/service-requests/{r['id']}/ratings", json={"rating": 5})
    eng.ok("POST", f"/service-requests/{r['id']}/ratings", json={"rating": 5})


def test_duration_limit_is_a_setting(world):
    owner, admin = world["owner"], world["admin"]
    owner.call("POST", "/service-requests", 400, json=request_body(owner, duration_working_days=100))
    admin.ok("PUT", "/admin/settings/model_b_max_working_days", json={"value": 120})
    owner.ok("POST", "/service-requests", json=request_body(owner, duration_working_days=100))
    admin.call("PUT", "/admin/settings/model_b_max_working_days", 400, json={"value": 0})
    logs = admin.ok("GET", "/admin/audit-logs?action=settings")["data"]
    assert logs and logs[0]["details"]["after"] == 120


def test_near_expiry_and_unverified_engineer(world):
    owner, admin = world["owner"], world["admin"]
    r = _active_contract(world)
    db = SessionLocal()
    c = db.query(ServiceContract).filter_by(request_id=r["id"]).one()
    end = c.end_date
    db.close()
    res = admin.ok("POST", "/admin/checks/run", json={})
    assert res["near_expiry"] == 0
    # Simulating a later date is a demo-mode feature; here demo mode is off, so it is refused.
    admin.call("POST", "/admin/checks/run", 400, json={"as_of": end.isoformat()})
    from app.services import checks
    db = SessionLocal()
    checks.run(db, end - timedelta(days=1))
    assert db.get(ServiceRequest, r["id"]).status == "near_expiry"
    db.close()
    _ = owner
