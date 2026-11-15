"""Review window (5 working days, 2 reminders, escalation, NO auto-approval) and the dispute process."""
from datetime import date

from app.database import SessionLocal
from app.models import Escalation, Notification, Project
from app.services import checks
from app.services.calendar import WorkCalendar, business_date
from tests.conftest import PDF, register
from tests.test_model_a import _to_in_progress


def _submitted(w):
    p, prop = _to_in_progress(w)
    d = w["owner"].ok("POST", f"/projects/{p['id']}/deliverables", json={"title": "Drawings"})
    w["eng"].ok("POST", f"/deliverables/{d['id']}/versions", files={"file": ("d.pdf", PDF)})
    w["eng"].ok("POST", f"/projects/{p['id']}/submit", json={})
    return p


def test_review_window_reminds_twice_then_escalates_without_approving(world):
    p = _submitted(world)
    db = SessionLocal()
    cal = WorkCalendar.load(db)
    proj = db.get(Project, p["id"])
    submitted_on = business_date(proj.submitted_at)
    assert proj.review_due_date == cal.add_working_days(submitted_on, 5)
    day3 = cal.add_working_days(submitted_on, 3)
    checks.run(db, day3)
    db.refresh(proj)
    assert proj.review_reminders_sent == 1
    checks.run(db, proj.review_due_date)
    db.refresh(proj)
    assert proj.review_reminders_sent == 2
    after = cal.add_working_days(proj.review_due_date, 1)
    checks.run(db, after)
    db.refresh(proj)
    assert proj.status == "submitted"                       # still pending – never approved automatically
    assert proj.review_escalated_at is not None
    assert db.query(Escalation).filter_by(project_id=p["id"], status="open").count() == 1
    kinds = {n.kind for n in db.query(Notification).all()}
    assert {"review_reminder", "review_overdue"} <= kinds
    checks.run(db, after)                                   # running again doesn't duplicate
    assert db.query(Escalation).filter_by(project_id=p["id"]).count() == 1
    db.close()
    assert len(world["admin"].ok("GET", "/admin/escalations")) == 1
    # The organization can still review normally afterwards; the escalation then closes itself
    v = world["owner"].ok("GET", f"/projects/{p['id']}/deliverables")[0]["versions"][0]
    world["owner"].ok("POST", f"/deliverable-versions/{v['id']}/review", json={"decision": "approved", "comment": ""})
    assert world["admin"].ok("GET", "/admin/escalations") == []
    assert len(world["admin"].ok("GET", "/admin/escalations?status=resolved")) == 1
    assert world["owner"].ok("POST", f"/projects/{p['id']}/approve")["status"] == "approved"
    _ = date


def test_dispute_pauses_payments_and_needs_reasoned_decision(world):
    owner, eng, eng2, admin = world["owner"], world["eng"], world["eng2"], world["admin"]
    p, _ = _to_in_progress(world)
    owner.ok("POST", f"/projects/{p['id']}/milestones", json={"title": "Stage 1", "amount_cents": 100000})
    d = owner.ok("POST", f"/projects/{p['id']}/deliverables", json={"title": "Report", "milestone_id": None})
    eng.ok("POST", f"/deliverables/{d['id']}/versions", files={"file": ("r.pdf", PDF)})
    v = owner.ok("GET", f"/projects/{p['id']}/deliverables")[0]["versions"][0]
    owner.ok("POST", f"/deliverable-versions/{v['id']}/review", json={"decision": "approved", "comment": ""})
    ms = owner.ok("GET", f"/projects/{p['id']}/milestones")
    inv = owner.ok("POST", f"/milestones/{ms[0]['id']}/approve")["invoice"]

    eng2.call("POST", "/disputes", 403, json={"subject_type": "project", "subject_id": p["id"], "reason_code": "payment",
                                              "description": "I am not part of this project at all."})
    dsp = eng.ok("POST", "/disputes", json={"subject_type": "project", "subject_id": p["id"], "reason_code": "payment",
                                            "description": "The approved milestone has not been paid for two weeks."})
    assert owner.ok("GET", f"/projects/{p['id']}")["status"] == "disputed"
    r = owner.call("POST", f"/invoices/{inv['id']}/pay", 409)                   # payments paused
    assert r.json()["error"]["code"] == "DISPUTE_OPEN"
    eng.call("POST", "/disputes", 409, json={"subject_type": "project", "subject_id": p["id"], "reason_code": "other",
                                             "description": "A second dispute on the same project."})
    eng2.call("GET", f"/disputes/{dsp['id']}", 404)                             # outsiders can't see it
    owner.ok("POST", f"/disputes/{dsp['id']}/entries", json={"body": "Payment was scheduled for next week."})
    assert admin.ok("GET", f"/disputes/{dsp['id']}")["status"] == "under_review"
    eng.ok("POST", f"/disputes/{dsp['id']}/evidence", files={"file": ("email.pdf", PDF)})
    ev = owner.ok("GET", f"/disputes/{dsp['id']}")["evidence"][0]
    assert owner.call("GET", f"/files/{ev['id']}").status_code == 200
    assert eng2.call("GET", f"/files/{ev['id']}").status_code == 404           # evidence is private

    admin.call("POST", f"/admin/disputes/{dsp['id']}/decision", 422,
               json={"outcome": "resume_work", "reasoning": "short", "resume_status": "in_progress"})
    admin.call("POST", f"/admin/disputes/{dsp['id']}/decision", 400,
               json={"outcome": "resume_work", "reasoning": "Long enough reasoning for the decision.", "resume_status": "completed_x"})
    admin.ok("POST", f"/admin/disputes/{dsp['id']}/decision",
             json={"outcome": "resume_work", "reasoning": "The milestone is due; the organization must pay it.",
                   "resume_status": "in_progress"})
    assert owner.ok("GET", f"/projects/{p['id']}")["status"] == "disputed"      # until closed / appeal window
    owner.call("POST", f"/invoices/{inv['id']}/pay", 409)                       # still paused during appeal window
    owner.ok("POST", f"/disputes/{dsp['id']}/appeal", json={"reason": "We disagree with the payment date assessment."})
    admin.ok("POST", f"/admin/disputes/{dsp['id']}/decision",
             json={"outcome": "resume_work", "reasoning": "After the appeal the decision stands: pay the milestone.",
                   "resume_status": "in_progress"})
    final = owner.ok("GET", f"/disputes/{dsp['id']}")
    assert final["status"] == "closed" and final["final_decision_text"]
    assert owner.ok("GET", f"/projects/{p['id']}")["status"] == "in_progress"
    owner.ok("POST", f"/invoices/{inv['id']}/pay")
    logs = [x["action"] for x in admin.ok("GET", "/admin/audit-logs?action=dispute")["data"]]
    assert {"dispute.opened", "dispute.decided", "dispute.appealed", "dispute.final_decision"} <= set(logs)


def test_refund_requires_decision(world):
    owner, eng, admin = world["owner"], world["eng"], world["admin"]
    p, _ = _to_in_progress(world)
    owner.ok("POST", f"/projects/{p['id']}/milestones", json={"title": "S1", "amount_cents": 50000})
    ms = owner.ok("GET", f"/projects/{p['id']}/milestones")
    inv = owner.ok("POST", f"/milestones/{ms[0]['id']}/approve")["invoice"]
    owner.ok("POST", f"/invoices/{inv['id']}/pay")
    dsp = owner.ok("POST", "/disputes", json={"subject_type": "project", "subject_id": p["id"], "reason_code": "quality",
                                              "description": "The first stage did not match the agreed scope."})
    r = admin.call("POST", f"/admin/invoices/{inv['id']}/refund", 409, json={"reason": "Quality dispute refund"})
    assert r.json()["error"]["code"] == "DECISION_REQUIRED"
    admin.ok("POST", f"/admin/disputes/{dsp['id']}/decision", json={"outcome": "refund_to_organization",
             "reasoning": "Stage 1 did not meet the agreed scope; refund it.", "resume_status": "in_progress"})
    tx = admin.ok("POST", f"/admin/invoices/{inv['id']}/refund", json={"reason": "Per dispute decision #1"})
    assert tx["kind"] == "refund"
    admin.call("POST", f"/admin/disputes/{dsp['id']}/close", 400, json={"note": ""})   # early close needs a reason
    admin.ok("POST", f"/admin/disputes/{dsp['id']}/close", json={"note": "Both parties accepted the decision."})
    _ = (eng, register)
