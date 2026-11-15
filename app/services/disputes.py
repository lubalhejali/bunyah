"""Disputes for both models. Rules:
- Only the parties (organization members with the right role, or the engineer) can open one.
- The project / contract becomes 'disputed'; billing and simulated payments pause.
- An administrator must record a reasoned decision. Money is never released or refunded automatically.
- Either party may appeal within the appeal window; an administrator then records the final decision.
- Every statement, response, note and decision is kept (dispute_entries) and sensitive steps go to the audit log.
"""
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import bad_request, conflict, forbidden, not_found
from app.models import (
    Dispute,
    DisputeEntry,
    DisputeStatus as D,
    OrgMember,
    Project,
    ProjectStatus as P,
    RequestStatus as R,
    ServiceContract,
    ServiceRequest,
    User,
)
from app.security import is_admin, org_context
from app.services import audit, notify, states
from app.services import settings as cfg
from app.services.calendar import WorkCalendar, today as biz_today
from app.services.model_a import event, user_mini

N = notify
REASONS = ("quality", "delay", "scope", "payment", "conduct", "time_records", "other")
OUTCOMES = ("release_to_engineer", "refund_to_organization", "partial_settlement", "resume_work",
            "no_financial_action")


def _subject(db: Session, d: Dispute) -> tuple[Project | ServiceRequest, int, int]:
    """(subject, org_id, engineer_id)"""
    if d.subject_type == "project":
        p = db.get(Project, d.project_id)
        return p, p.org_id, p.freelancer_id
    r = db.get(ServiceRequest, d.request_id)
    c = db.scalar(select(ServiceContract).where(ServiceContract.request_id == r.id))
    return r, r.org_id, c.engineer_id if c else None


def side_of(db: Session, user: User, org_id: int, engineer_id: int | None) -> str | None:
    if user.id == engineer_id:
        return "engineer"
    if db.scalar(select(OrgMember.id).where(OrgMember.user_id == user.id, OrgMember.org_id == org_id,
                                            OrgMember.is_active.is_(True))):
        return "organization"
    return "admin" if is_admin(user) else None


def is_party(db: Session, user: User, d: Dispute) -> bool:
    _, org_id, eng_id = _subject(db, d)
    return side_of(db, user, org_id, eng_id) is not None


def get_dispute(db: Session, dispute_id: int, user: User) -> tuple[Dispute, str]:
    d = db.get(Dispute, dispute_id)
    if d is None:
        raise not_found("Dispute", "النزاع")
    _, org_id, eng_id = _subject(db, d)
    side = side_of(db, user, org_id, eng_id)
    if side is None:
        raise not_found("Dispute", "النزاع")
    return d, side


def open_dispute(db: Session, user: User, subject_type: str, subject_id: int, reason: str, description: str) -> Dispute:
    if reason not in REASONS:
        raise bad_request("Choose a dispute reason.", "اختر سبب النزاع.")
    cal = WorkCalendar.load(db)
    target = cal.add_working_days(biz_today(), int(cfg.get(db, "dispute_target_working_days")))
    if subject_type == "project":
        p = db.get(Project, subject_id, with_for_update=True, populate_existing=True)
        if p is None or p.freelancer_id is None:
            raise not_found("Project", "المشروع")
        side = side_of(db, user, p.org_id, p.freelancer_id)
        _check_raiser(db, user, side)
        if db.scalar(select(Dispute.id).where(Dispute.project_id == p.id, Dispute.status.in_(D.ACTIVE))):
            raise conflict("There is already an open dispute on this project.", "يوجد نزاع مفتوح على هذا المشروع.")
        prev = p.status
        states.check(states.PROJECT_FLOW, p.status, P.DISPUTED)
        p.status, p.status_before_dispute = P.DISPUTED, prev
        d = Dispute(subject_type="project", project_id=p.id, raised_by=user.id, raised_by_side=side,
                    reason_code=reason, description=description, target_resolution_date=target)
        title, org_id, eng_id = p.title, p.org_id, p.freelancer_id
        event(db, user, "Dispute opened. Work, approvals and payments are paused.",
              "تم فتح نزاع. توقف العمل والاعتمادات والمدفوعات مؤقتًا.", project_id=p.id)
    elif subject_type == "contract":
        r = db.get(ServiceRequest, subject_id, with_for_update=True, populate_existing=True)
        c = db.scalar(select(ServiceContract).where(ServiceContract.request_id == subject_id)) if r else None
        if r is None or c is None:
            raise not_found("Contract", "العقد")
        side = side_of(db, user, r.org_id, c.engineer_id)
        _check_raiser(db, user, side)
        if db.scalar(select(Dispute.id).where(Dispute.request_id == r.id, Dispute.status.in_(D.ACTIVE))):
            raise conflict("There is already an open dispute on this contract.", "يوجد نزاع مفتوح على هذا العقد.")
        prev = r.status
        states.check(states.REQUEST_FLOW, r.status, R.DISPUTED)
        r.status, r.status_before_dispute = R.DISPUTED, prev
        d = Dispute(subject_type="contract", request_id=r.id, raised_by=user.id, raised_by_side=side,
                    reason_code=reason, description=description, target_resolution_date=target)
        title, org_id, eng_id = r.title, r.org_id, c.engineer_id
        event(db, user, "Dispute opened. Billing approvals and payments are paused.",
              "تم فتح نزاع. توقفت اعتمادات الفوترة والمدفوعات مؤقتًا.", request_id=r.id)
    else:
        raise bad_request("Unknown dispute subject.", "موضوع النزاع غير معروف.")
    db.add(d)
    db.flush()
    db.add(DisputeEntry(dispute_id=d.id, author_id=user.id, author_side=side, kind="statement", body=description))
    others = N.org_user_ids(db, org_id, N.MANAGERS) if side == "engineer" else [eng_id]
    N.notify(db, others + N.admin_user_ids(db), "dispute_opened", title, f"/disputes/{d.id}")
    audit.record(db, user, "dispute.opened", "dispute", d.id, subject=subject_type, subject_id=subject_id,
                 reason=reason)
    return d


def _check_raiser(db: Session, user: User, side: str | None) -> None:
    if side not in ("organization", "engineer"):
        raise forbidden("Only the parties can open a dispute.", "يمكن لأطراف العمل فقط فتح نزاع.")
    if side == "organization":
        ctx = org_context(db, user)
        ctx.require("dispute.raise")


def add_entry(db: Session, user: User, d: Dispute, side: str, body: str) -> DisputeEntry:
    if d.status == D.CLOSED:
        raise conflict("This dispute is closed.", "هذا النزاع مغلق.")
    if side == "organization":
        ctx = org_context(db, user)
        if not (ctx.can("dispute.raise") or ctx.can("work.review")):
            raise forbidden()
    kind = "admin_note" if side == "admin" else ("statement" if side == d.raised_by_side else "response")
    e = DisputeEntry(dispute_id=d.id, author_id=user.id, author_side=side, kind=kind, body=body)
    db.add(e)
    if kind == "response" and d.status == D.OPEN:
        d.status = D.UNDER_REVIEW
    subject, org_id, eng_id = _subject(db, d)
    targets = (N.org_user_ids(db, org_id, N.MANAGERS) + [eng_id] + N.admin_user_ids(db))
    N.notify(db, [t for t in targets if t != user.id], "dispute_response", subject.title, f"/disputes/{d.id}")
    return e


def start_review(db: Session, admin: User, d: Dispute) -> None:
    states.require_status(d.status, D.OPEN)
    d.status = D.UNDER_REVIEW
    db.add(DisputeEntry(dispute_id=d.id, author_id=admin.id, author_side="admin", kind="admin_note",
                        body="Administrative review started."))
    audit.record(db, admin, "dispute.review_started", "dispute", d.id)


def _resume_options(d: Dispute) -> set[str]:
    return states.PROJECT_FLOW[P.DISPUTED] if d.subject_type == "project" else states.REQUEST_FLOW[R.DISPUTED]


def decide(db: Session, admin: User, d: Dispute, outcome: str, reasoning: str, resume_status: str) -> None:
    if d.status not in (D.OPEN, D.UNDER_REVIEW, D.APPEALED):
        raise conflict("A decision can't be recorded at this stage.", "لا يمكن تسجيل قرار في هذه المرحلة.")
    if outcome not in OUTCOMES:
        raise bad_request("Choose a decision outcome.", "اختر نتيجة القرار.")
    if len(reasoning.strip()) < 20:
        raise bad_request("Write the reasons for the decision (at least 20 characters).",
                          "اكتب أسباب القرار (20 حرفًا على الأقل).", "REASONS_REQUIRED")
    if resume_status not in _resume_options(d):
        raise bad_request("Choose the status the work returns to.", "اختر الحالة التي يعود إليها العمل.")
    subject, org_id, eng_id = _subject(db, d)
    subject.status_before_dispute = resume_status  # applied when the dispute is closed
    final = d.status == D.APPEALED
    d.decision_outcome, d.decided_by, d.decided_at = outcome, admin.id, datetime.now(UTC)
    if final:
        d.final_decision_text = reasoning
    else:
        d.decision_text = reasoning
        cal = WorkCalendar.load(db)
        d.appeal_deadline = cal.add_working_days(biz_today(), int(cfg.get(db, "appeal_window_working_days")))
    db.add(DisputeEntry(dispute_id=d.id, author_id=admin.id, author_side="admin", kind="decision",
                        body=f"[{outcome}] {reasoning}"))
    audit.record(db, admin, "dispute.final_decision" if final else "dispute.decided", "dispute", d.id,
                 outcome=outcome, resume_status=resume_status)
    N.notify(db, N.org_user_ids(db, org_id, N.MANAGERS) + [eng_id], "dispute_decided", subject.title,
             f"/disputes/{d.id}")
    if final:
        _close(db, admin, d, subject, org_id, eng_id)
    else:
        d.status = D.DECIDED


def appeal(db: Session, user: User, d: Dispute, side: str, reason: str) -> None:
    if side not in ("organization", "engineer"):
        raise forbidden()
    states.require_status(d.status, D.DECIDED)
    if d.appeal_deadline and biz_today() > d.appeal_deadline:
        raise conflict("The appeal window has closed.", "انتهت مهلة الاستئناف.", "APPEAL_CLOSED")
    if len(reason.strip()) < 20:
        raise bad_request("Explain why you are appealing (at least 20 characters).",
                          "وضّح سبب الاستئناف (20 حرفًا على الأقل).", "REASONS_REQUIRED")
    d.status, d.appeal_reason, d.appealed_by = D.APPEALED, reason, user.id
    db.add(DisputeEntry(dispute_id=d.id, author_id=user.id, author_side=side, kind="appeal", body=reason))
    subject, org_id, eng_id = _subject(db, d)
    audit.record(db, user, "dispute.appealed", "dispute", d.id)
    N.notify(db, N.admin_user_ids(db) + N.org_user_ids(db, org_id, N.MANAGERS) + [eng_id], "dispute_appealed",
             subject.title, f"/disputes/{d.id}")


def close(db: Session, admin: User, d: Dispute, note: str) -> None:
    states.require_status(d.status, D.DECIDED)
    early = d.appeal_deadline is not None and biz_today() <= d.appeal_deadline
    if early and len(note.strip()) < 10:
        raise bad_request("The appeal window is still open. Record why the dispute is closed early "
                          "(e.g. both parties accepted the decision).",
                          "مهلة الاستئناف ما زالت مفتوحة. اذكر سبب الإغلاق المبكر (مثل قبول الطرفين للقرار).",
                          "NOTE_REQUIRED")
    if note:
        db.add(DisputeEntry(dispute_id=d.id, author_id=admin.id, author_side="admin", kind="admin_note", body=note))
    subject, org_id, eng_id = _subject(db, d)
    audit.record(db, admin, "dispute.closed", "dispute", d.id, early=early)
    _close(db, admin, d, subject, org_id, eng_id)


def _close(db: Session, admin: User, d: Dispute, subject, org_id: int, eng_id: int) -> None:
    resume = subject.status_before_dispute
    flow = states.PROJECT_FLOW if d.subject_type == "project" else states.REQUEST_FLOW
    states.check(flow, subject.status, resume)
    subject.status = resume
    d.status, d.closed_at = D.CLOSED, datetime.now(UTC)
    if d.subject_type == "project":
        event(db, admin, f"Dispute closed. Status set to '{resume}'.", "أُغلق النزاع وتم تحديث الحالة.",
              project_id=subject.id)
    else:
        event(db, admin, f"Dispute closed. Status set to '{resume}'.", "أُغلق النزاع وتم تحديث الحالة.",
              request_id=subject.id)
    N.notify(db, N.org_user_ids(db, org_id, N.MANAGERS) + [eng_id], "dispute_closed", subject.title,
             f"/disputes/{d.id}")


def dispute_out(db: Session, d: Dispute, side: str, full: bool = True) -> dict:
    subject, org_id, eng_id = _subject(db, d)
    out = {"id": d.id, "subject_type": d.subject_type, "subject_id": subject.id, "subject_title": subject.title,
           "status": d.status, "reason_code": d.reason_code, "raised_by_side": d.raised_by_side,
           "raised_by": user_mini(d.raiser), "target_resolution_date": d.target_resolution_date,
           "overdue": d.status in (D.OPEN, D.UNDER_REVIEW) and biz_today() > d.target_resolution_date,
           "decision_outcome": d.decision_outcome, "decided_at": d.decided_at,
           "appeal_deadline": d.appeal_deadline, "created_at": d.created_at, "closed_at": d.closed_at,
           "my_side": side}
    if full:
        from app.models import StoredFile
        from app.services.files import file_out
        entries = db.scalars(select(DisputeEntry).where(DisputeEntry.dispute_id == d.id).order_by(DisputeEntry.id)).all()
        files = db.scalars(select(StoredFile).where(StoredFile.context_type == "dispute",
                                                    StoredFile.context_id == d.id)).all()
        out |= {"description": d.description, "decision_text": d.decision_text, "appeal_reason": d.appeal_reason,
                "final_decision_text": d.final_decision_text,
                "resume_options": sorted(_resume_options(d)), "outcomes": list(OUTCOMES),
                "entries": [{"id": e.id, "kind": e.kind, "author_side": e.author_side, "author": user_mini(e.author),
                             "body": e.body, "created_at": e.created_at} for e in entries],
                "evidence": [file_out(f) for f in files]}
    return out
