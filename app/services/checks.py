"""Daily checks: review reminders, review-window escalations, closing expired proposal windows and
marking contracts that are close to their end. Runs when the app starts, at most once an hour while people
use the site, and on demand from the admin page.

IMPORTANT: a review window that passes NEVER approves anything. The item stays pending, both parties are
notified, and an escalation is opened for the BUNYAH team.
"""
import threading
import time
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BillingPeriod,
    Escalation,
    Project,
    ProjectStatus as P,
    RequestStatus as R,
    ServiceContract,
    ServiceRequest,
)
from app.services import notify, states
from app.services import settings as cfg
from app.services.calendar import WorkCalendar, business_date, today as biz_today
from app.services.model_a import event

N = notify
_last_run = 0.0
_lock = threading.Lock()


def _review_step(db: Session, cal: WorkCalendar, today: date, submitted_on: date, due: date, sent: int,
                 escalated: bool) -> str | None:
    """Decides what is due today: 'reminder1', 'reminder2' (on the last day), 'escalate' (after it) or nothing."""
    if escalated:
        return None
    if today > due:
        return "escalate"
    elapsed = cal.working_days_between(submitted_on + timedelta(days=1), today)  # working days since submission
    if sent == 0 and elapsed >= int(cfg.get(db, "review_first_reminder_day")):
        return "reminder1"
    if sent == 1 and today >= due:
        return "reminder2"
    return None


def run(db: Session, today: date | None = None) -> dict:
    today = today or biz_today()
    cal = WorkCalendar.load(db)
    out = {"reminders": 0, "escalations": 0, "closed_proposal_windows": 0, "near_expiry": 0}

    # Model A: deliverables waiting for the organization's review
    for p in db.scalars(select(Project).where(Project.status.in_(P.IN_REVIEW),
                                              Project.review_due_date.is_not(None))).all():
        step = _review_step(db, cal, today, business_date(p.submitted_at), p.review_due_date, p.review_reminders_sent,
                            p.review_escalated_at is not None)
        if step in ("reminder1", "reminder2"):
            p.review_reminders_sent = 1 if step == "reminder1" else 2
            N.notify(db, N.org_user_ids(db, p.org_id, N.REVIEWERS), "review_reminder", p.title, f"/projects/{p.id}")
            out["reminders"] += 1
        elif step == "escalate":
            p.review_escalated_at = datetime.now(UTC)
            db.add(Escalation(kind="deliverable_review", project_id=p.id,
                              note=f"Review window ended on {p.review_due_date.isoformat()} without a decision."))
            event(db, None, "Review window passed. Deliverables stay pending; escalated to the BUNYAH team.",
                  "انتهت مهلة المراجعة. تبقى التسليمات معلقة وتم التصعيد لفريق بُنية.", project_id=p.id)
            N.notify(db, N.org_user_ids(db, p.org_id) + [p.freelancer_id] + N.admin_user_ids(db), "review_overdue",
                     p.title, f"/projects/{p.id}")
            out["escalations"] += 1

    # Model B: billing periods waiting for approval
    for bp in db.scalars(select(BillingPeriod).where(BillingPeriod.status == "submitted",
                                                     BillingPeriod.review_due_date.is_not(None))).all():
        c = db.get(ServiceContract, bp.contract_id)
        r = db.get(ServiceRequest, c.request_id)
        step = _review_step(db, cal, today, business_date(bp.submitted_at), bp.review_due_date, bp.review_reminders_sent,
                            bp.review_escalated_at is not None)
        if step in ("reminder1", "reminder2"):
            bp.review_reminders_sent = 1 if step == "reminder1" else 2
            N.notify(db, N.org_user_ids(db, r.org_id, N.MANAGERS), "review_reminder", r.title, f"/services/{r.id}")
            out["reminders"] += 1
        elif step == "escalate":
            bp.review_escalated_at = datetime.now(UTC)
            db.add(Escalation(kind="period_review", period_id=bp.id,
                              note=f"Billing period {bp.seq} of '{r.title}' not reviewed by "
                                   f"{bp.review_due_date.isoformat()}."))
            event(db, None, f"Billing period {bp.seq}: review window passed; escalated to the BUNYAH team.",
                  f"فترة الفوترة {bp.seq}: انتهت مهلة المراجعة وتم التصعيد لفريق بُنية.", request_id=r.id)
            N.notify(db, N.org_user_ids(db, r.org_id) + [c.engineer_id] + N.admin_user_ids(db), "review_overdue",
                     r.title, f"/services/{r.id}")
            out["escalations"] += 1

    # Model A: proposal deadline passed -> stop accepting proposals
    for p in db.scalars(select(Project).where(Project.status == P.PUBLISHED, Project.proposal_deadline.is_not(None),
                                              Project.proposal_deadline < today)).all():
        states.check(states.PROJECT_FLOW, p.status, P.APPLICATIONS_CLOSED)
        p.status = P.APPLICATIONS_CLOSED
        event(db, None, "Proposal deadline passed. Submissions closed.", "انتهى موعد العروض وأُغلق الاستقبال.",
              project_id=p.id)
        out["closed_proposal_windows"] += 1

    # Model B: contract close to its end
    near = int(cfg.get(db, "near_expiry_working_days"))
    for r in db.scalars(select(ServiceRequest).where(ServiceRequest.status == R.ACTIVE)).all():
        c = db.scalar(select(ServiceContract).where(ServiceContract.request_id == r.id))
        if c and cal.working_days_between(today, c.end_date) <= near:
            r.status = R.NEAR_EXPIRY
            event(db, None, "Contract is close to its end date.", "يقترب العقد من تاريخ انتهائه.", request_id=r.id)
            N.notify(db, N.org_user_ids(db, r.org_id, N.MANAGERS) + [c.engineer_id], "contract_near_expiry", r.title,
                     f"/services/{r.id}")
            out["near_expiry"] += 1
    db.commit()
    return out


def run_if_due(db: Session) -> None:
    """Called on normal page loads; runs the checks at most once an hour."""
    global _last_run
    with _lock:
        if time.monotonic() - _last_run < 3600:
            return
        _last_run = time.monotonic()
    run(db)


def reset_timer() -> None:
    global _last_run
    _last_run = 0.0
