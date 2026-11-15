"""Administrator dashboard API. Every sensitive action is written to the audit log."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import schemas as s
from app.config import get_settings
from app.database import get_db
from app.errors import bad_request, conflict, not_found
from app.models import (
    AuditLog,
    Discipline,
    Dispute,
    DisputeStatus,
    EngineerProfile,
    Escalation,
    FeeRule,
    Holiday,
    Organization,
    Offer,
    Payment,
    Project,
    Rating,
    Review,
    Role,
    ServiceApplication,
    ServiceContract,
    ServiceRequest,
    SimInvoice,
    SimTransaction,
    StoredFile,
    User,
    Verification,
    VerificationRequest,
    Withdrawal,
)
from app.security import client_ip, is_admin, require_admin
from app.services import audit, checks, finance, notify
from app.services import disputes as D
from app.services import files as filesvc
from app.services import model_a as A
from app.services import model_b as B
from app.services import settings as cfg
from app.services.serialize import engineer_private, org_private
from app.services.calendar import today as biz_today

router = APIRouter(prefix="/admin", tags=["admin"])


def _count(db: Session, stmt) -> int:
    return int(db.scalar(stmt) or 0)


# ---------- overview / analytics ----------
@router.get("/overview")
def overview(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    def by(col, model):
        return dict(db.execute(select(col, func.count(model.id)).group_by(col)).all())

    disciplines = {d.id: d for d in db.scalars(select(Discipline)).all()}
    proj_disc = db.execute(select(Project.discipline_id, func.count(Project.id)).group_by(Project.discipline_id)).all()
    req_disc = db.execute(select(ServiceRequest.discipline_id, func.count(ServiceRequest.id))
                          .group_by(ServiceRequest.discipline_id)).all()
    paid = db.scalars(select(SimInvoice).where(SimInvoice.status == "paid")).all()
    today = biz_today()
    return {
        "users_by_role": dict(db.execute(select(User.role, func.count(User.id)).group_by(User.role)).all()),
        "organizations_by_verification": by(Organization.verification_status, Organization),
        "engineers_by_verification": dict(db.execute(select(EngineerProfile.verification_status,
                                                            func.count(EngineerProfile.user_id))
                                                     .group_by(EngineerProfile.verification_status)).all()),
        "projects_by_status": by(Project.status, Project),
        "requests_by_status": by(ServiceRequest.status, ServiceRequest),
        "proposals_total": _count(db, select(func.count(Offer.id))),
        "applications_total": _count(db, select(func.count(ServiceApplication.id))),
        "contracts_total": _count(db, select(func.count(ServiceContract.id))),
        "verifications_pending": _count(db, select(func.count(VerificationRequest.id)).where(
            VerificationRequest.status == Verification.PENDING)),
        "requests_waiting_review": _count(db, select(func.count(ServiceRequest.id)).where(
            ServiceRequest.status.in_(("submitted", "pending_review")))),
        "disputes_active": _count(db, select(func.count(Dispute.id)).where(Dispute.status.in_(DisputeStatus.ACTIVE))),
        "disputes_overdue": _count(db, select(func.count(Dispute.id)).where(
            Dispute.status.in_(("open", "under_review")), Dispute.target_resolution_date < today)),
        "escalations_open": _count(db, select(func.count(Escalation.id)).where(Escalation.status == "open")),
        "simulated_finance": {
            "paid_volume_cents": sum(i.subtotal_cents for i in paid),
            "platform_fees_cents": sum(i.org_fee_cents + i.engineer_fee_cents for i in paid),
            "invoices_unpaid": _count(db, select(func.count(SimInvoice.id)).where(SimInvoice.status == "issued")),
            "payouts_pending": _count(db, select(func.count(SimTransaction.id)).where(
                SimTransaction.kind == "payout", SimTransaction.status == "pending")),
        },
        "by_discipline": [
            {"discipline": A.discipline_out(disciplines.get(k)) if k else None, "projects": v,
             "requests": dict(req_disc).get(k, 0)} for k, v in proj_disc
        ] + [{"discipline": A.discipline_out(disciplines.get(k)) if k else None, "projects": 0, "requests": v}
             for k, v in req_disc if k not in dict(proj_disc)],
        "average_engineer_rating": db.scalar(select(func.avg(Rating.rating)).where(Rating.reviewer_side == "organization")),
    }


# ---------- users ----------
@router.get("/users")
def users(q: str = "", role: str = "", page: int = 1, per_page: int = 30, db: Session = Depends(get_db),
          _: User = Depends(require_admin)):
    per_page, page = max(1, min(per_page, 100)), max(page, 1)
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if q:
        like = f"%{q.strip()[:80]}%"
        stmt = stmt.where(or_(User.name.ilike(like), User.email.ilike(like)))
    total = _count(db, select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(User.id.desc()).offset((page - 1) * per_page).limit(per_page)).all()
    out = []
    for u in rows:
        org = u.membership.org if u.membership else None
        out.append({"id": u.id, "name": u.name, "email": u.email, "role": u.role, "is_active": u.is_active,
                    "is_admin": is_admin(u), "created_at": u.created_at, "last_login_at": u.last_login_at,
                    "organization": org.name if org else None,
                    "org_role": u.membership.org_role if u.membership else None,
                    "verification_status": (org.verification_status if org else
                                            (u.engineer_profile.verification_status if u.engineer_profile else None))})
    return {"data": out, "total": total, "page": page, "per_page": per_page}


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: s.UserAdminUpdate, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    u = db.get(User, user_id)
    if u is None:
        raise not_found("User", "المستخدم")
    if u.id == admin.id:
        raise conflict("You can't suspend your own account.", "لا يمكنك إيقاف حسابك.")
    u.is_active = body.is_active
    audit.record(db, admin, "user.activated" if body.is_active else "user.suspended", "user", u.id, ip=client_ip(request))
    db.commit()
    return {"id": u.id, "is_active": u.is_active}


# ---------- verification ----------
def _verification_out(db: Session, v: VerificationRequest, full: bool = False) -> dict:
    if v.subject_type == "organization":
        o = db.get(Organization, v.subject_id)
        subject = org_private(db, o) if full else {"id": o.id, "name": o.name}
    else:
        u = db.get(User, v.subject_id)
        subject = engineer_private(db, u) | {"email": u.email} if full else {"id": u.id, "name": u.name}
    out = {"id": v.id, "subject_type": v.subject_type, "subject": subject, "status": v.status,
           "applicant_note": v.applicant_note, "reviewer_note": v.reviewer_note, "created_at": v.created_at,
           "reviewed_at": v.reviewed_at}
    if full:
        out["documents"] = [filesvc.file_out(f) for f in db.scalars(select(StoredFile).where(
            StoredFile.context_type == "verification", StoredFile.context_id == v.id)).all()]
    return out


@router.get("/verifications")
def verifications(status: str = "pending", db: Session = Depends(get_db), _: User = Depends(require_admin)):
    stmt = select(VerificationRequest)
    if status:
        stmt = stmt.where(VerificationRequest.status == status)
    return [_verification_out(db, v) for v in db.scalars(stmt.order_by(VerificationRequest.id))]


@router.get("/verifications/{vid}")
def verification(vid: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    v = db.get(VerificationRequest, vid)
    if v is None:
        raise not_found("Verification request", "طلب التوثيق")
    return _verification_out(db, v, full=True)


@router.post("/verifications/{vid}/decision")
def decide_verification(vid: int, body: s.VerificationDecision, request: Request, db: Session = Depends(get_db),
                        admin: User = Depends(require_admin)):
    v = db.get(VerificationRequest, vid)
    if v is None:
        raise not_found("Verification request", "طلب التوثيق")
    if v.status != Verification.PENDING:
        raise conflict("This request was already decided.", "تم البت في هذا الطلب مسبقًا.")
    if body.decision in ("reject", "needs_info") and len(body.note) < 5:
        raise bad_request("Explain the reason to the applicant.", "وضّح السبب لمقدم الطلب.", "NOTE_REQUIRED")
    new = {"approve": Verification.VERIFIED, "reject": Verification.REJECTED,
           "needs_info": Verification.NEEDS_INFO}[body.decision]
    v.status, v.reviewer_note, v.reviewer_id, v.reviewed_at = new, body.note, admin.id, datetime.now(UTC)
    kind = {"approve": "verification_approved", "reject": "verification_rejected",
            "needs_info": "verification_needs_info"}[body.decision]
    if v.subject_type == "organization":
        o = db.get(Organization, v.subject_id)
        o.verification_status = new
        notify.notify(db, notify.org_user_ids(db, o.id, ("owner",)), kind, o.name, "/organization")
    else:
        u = db.get(User, v.subject_id)
        u.engineer_profile.verification_status = new
        notify.notify(db, [u.id], kind, u.name, "/profile")
    audit.record(db, admin, f"verification.{body.decision}", v.subject_type, v.subject_id, ip=client_ip(request),
                 request_id=v.id, note=body.note)
    db.commit()
    return _verification_out(db, v)


# ---------- monitoring lists ----------
@router.get("/projects")
def projects(status: str = "", q: str = "", db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    stmt = select(Project)
    if status:
        stmt = stmt.where(Project.status == status)
    if q:
        stmt = stmt.where(Project.title.ilike(f"%{q.strip()[:80]}%"))
    rows = db.scalars(stmt.order_by(Project.id.desc()).limit(300)).all()
    return [A.project_out(db, p, brief=True) | {"engineer": A.user_mini(p.freelancer),
                                                 "review_escalated": p.review_escalated_at is not None}
            for p in rows]


@router.get("/service-requests")
def service_requests(status: str = "", db: Session = Depends(get_db), _: User = Depends(require_admin)):
    stmt = select(ServiceRequest)
    if status == "review":
        stmt = stmt.where(ServiceRequest.status.in_(("submitted", "pending_review")))
    elif status:
        stmt = stmt.where(ServiceRequest.status == status)
    return [B.request_out(db, r) for r in db.scalars(stmt.order_by(ServiceRequest.id.desc()).limit(300))]


@router.post("/service-requests/{request_id}/review")
def review_request(request_id: int, body: s.RequestReviewIn, request: Request, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    r = db.get(ServiceRequest, request_id)
    if r is None:
        raise not_found("Service request", "طلب الخدمة")
    B.admin_review(db, admin, r, body.decision, body.note)
    audit.record(db, admin, f"service_request.{body.decision}", "service_request", r.id, ip=client_ip(request),
                 note=body.note)
    db.commit()
    return B.request_out(db, r)


@router.get("/proposals")
def proposals(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.scalars(select(Offer).order_by(Offer.id.desc()).limit(300)).all()
    return [A.proposal_out(db, o, full=False) for o in rows]


@router.get("/applications")
def applications(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.scalars(select(ServiceApplication).order_by(ServiceApplication.id.desc()).limit(300)).all()
    return [B.application_out(db, a) for a in rows]


@router.get("/contracts")
def contracts(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.scalars(select(ServiceContract).order_by(ServiceContract.id.desc()).limit(300)).all()
    out = []
    for c in rows:
        r = db.get(ServiceRequest, c.request_id)
        out.append({"request_id": r.id, "title": r.title, "status": r.status, "organization": r.org.name,
                    "engineer": A.user_mini(c.engineer), "start_date": c.start_date, "end_date": c.end_date,
                    "working_days": c.working_days, "daily_rate_cents": c.daily_rate_cents,
                    "periods_submitted": sum(p.status == "submitted" for p in c.periods),
                    "periods_approved": sum(p.status == "approved" for p in c.periods)})
    return out


# ---------- disputes ----------
def _dispute(db: Session, dispute_id: int) -> Dispute:
    d = db.get(Dispute, dispute_id)
    if d is None:
        raise not_found("Dispute", "النزاع")
    return d


@router.post("/disputes/{dispute_id}/start-review")
def dispute_start(dispute_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    d = _dispute(db, dispute_id)
    D.start_review(db, admin, d)
    db.commit()
    return D.dispute_out(db, d, "admin")


@router.post("/disputes/{dispute_id}/decision")
def dispute_decide(dispute_id: int, body: s.DisputeDecisionIn, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    d = _dispute(db, dispute_id)
    D.decide(db, admin, d, body.outcome, body.reasoning, body.resume_status)
    db.commit()
    return D.dispute_out(db, d, "admin")


@router.post("/disputes/{dispute_id}/close")
def dispute_close(dispute_id: int, body: s.NoteIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    d = _dispute(db, dispute_id)
    D.close(db, admin, d, body.note)
    db.commit()
    return D.dispute_out(db, d, "admin")


# ---------- simulated finance ----------
@router.get("/finance")
def all_finance(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    invs = db.scalars(select(SimInvoice).order_by(SimInvoice.id.desc()).limit(500)).all()
    txs = db.scalars(select(SimTransaction).order_by(SimTransaction.id.desc()).limit(500)).all()
    orgs = {o.id: o.name for o in db.scalars(select(Organization)).all()}
    names = {u.id: u.name for u in db.scalars(select(User).where(User.role == Role.ENGINEER)).all()}
    return {"simulated": True,
            "invoices": [finance.invoice_out(i) | {"org_name": orgs.get(i.org_id), "engineer_name": names.get(i.engineer_id)}
                         for i in invs],
            "transactions": [finance.tx_out(t) | {"org_name": orgs.get(t.org_id), "engineer_name": names.get(t.engineer_id)}
                             for t in txs]}


@router.post("/payouts/{tx_id}/mark-sent")
def payout_sent(tx_id: int, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    tx = db.get(SimTransaction, tx_id)
    if tx is None:
        raise not_found("Transaction", "العملية")
    finance.mark_payout_sent(db, admin, tx)
    audit.record(db, admin, "finance.simulated_payout_sent", "transaction", tx.id, ip=client_ip(request),
                 amount=tx.gross_cents - tx.engineer_fee_cents)
    notify.notify(db, [tx.engineer_id], "payout_sent", tx.ref, "/finance")
    db.commit()
    return finance.tx_out(tx)


@router.post("/invoices/{invoice_id}/refund")
def refund(invoice_id: int, body: s.RefundIn, request: Request, db: Session = Depends(get_db),
           admin: User = Depends(require_admin)):
    inv = db.get(SimInvoice, invoice_id)
    if inv is None:
        raise not_found("Invoice", "الفاتورة")
    tx = finance.record_refund(db, admin, inv, body.reason)
    audit.record(db, admin, "finance.simulated_refund", "invoice", inv.id, ip=client_ip(request),
                 amount=inv.total_cents, reason=body.reason)
    db.commit()
    return finance.tx_out(tx)


@router.get("/fee-rules")
def fee_rules(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return [finance.rule_out(r) for r in db.scalars(select(FeeRule).order_by(FeeRule.id.desc()))]


@router.post("/fee-rules", status_code=201)
def new_fee_rule(body: s.FeeRuleIn, request: Request, db: Session = Depends(get_db),
                 admin: User = Depends(require_admin)):
    old = finance.active_rule(db, body.model)
    r = finance.save_rule(db, admin, body.model, body.payer, body.fee_type, body.org_value, body.engineer_value,
                          body.note)
    audit.record(db, admin, "finance.fee_rule_changed", "fee_rule", r.id, ip=client_ip(request), model=body.model,
                 before=str(finance.rule_out(old)) if old else "none", after=str(finance.rule_out(r)))
    db.commit()
    return finance.rule_out(r)


# ---------- settings ----------
@router.get("/settings")
def settings(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return cfg.all_settings(db)


@router.put("/settings/{key}")
def set_setting(key: str, body: s.SettingIn, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    old, new = cfg.set_value(db, key, body.value, admin.id)
    audit.record(db, admin, "settings.changed", "setting", None, ip=client_ip(request), key=key, before=old, after=new)
    db.commit()
    return {"key": key, "value": new}


# ---------- disciplines ----------
@router.get("/disciplines")
def all_disciplines(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.scalars(select(Discipline).order_by(Discipline.sort_order, Discipline.name_en)).all()
    return [A.discipline_out(d) | {"is_active": d.is_active, "sort_order": d.sort_order} for d in rows]


@router.post("/disciplines", status_code=201)
def add_discipline(body: s.DisciplineIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.scalar(select(Discipline.id).where(Discipline.code == body.code)):
        raise conflict("A discipline with this code exists.", "يوجد تخصص بهذا الرمز.")
    d = Discipline(**body.model_dump())
    db.add(d)
    db.flush()
    audit.record(db, admin, "discipline.created", "discipline", d.id, code=d.code)
    db.commit()
    return A.discipline_out(d)


@router.patch("/disciplines/{discipline_id}")
def edit_discipline(discipline_id: int, body: s.DisciplineUpdate, db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    d = db.get(Discipline, discipline_id)
    if d is None:
        raise not_found("Discipline", "التخصص")
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(d, k, v)
    audit.record(db, admin, "discipline.updated", "discipline", d.id)
    db.commit()
    return A.discipline_out(d) | {"is_active": d.is_active}


# ---------- holidays (working-day calendar) ----------
@router.get("/holidays")
def holidays(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return [{"id": h.id, "day": h.day, "name_en": h.name_en, "name_ar": h.name_ar, "is_confirmed": h.is_confirmed}
            for h in db.scalars(select(Holiday).order_by(Holiday.day))]


@router.post("/holidays", status_code=201)
def add_holiday(body: s.HolidayIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.scalar(select(Holiday.id).where(Holiday.day == body.day)):
        raise conflict("That date is already a holiday.", "هذا التاريخ مسجل كعطلة.")
    h = Holiday(**body.model_dump())
    db.add(h)
    db.flush()
    audit.record(db, admin, "calendar.holiday_added", "holiday", h.id, day=str(body.day))
    db.commit()
    return {"id": h.id}


@router.delete("/holidays/{holiday_id}", status_code=204)
def delete_holiday(holiday_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    h = db.get(Holiday, holiday_id)
    if h is None:
        raise not_found("Holiday", "العطلة")
    audit.record(db, admin, "calendar.holiday_removed", "holiday", h.id, day=str(h.day))
    db.delete(h)
    db.commit()
    return Response(status_code=204)


# ---------- notifications ----------
@router.post("/announcements", status_code=201)
def announce(body: s.AnnouncementIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    stmt = select(User.id).where(User.is_active.is_(True))
    if body.audience != "all":
        stmt = stmt.where(User.role == body.audience)
    ids = list(db.scalars(stmt).all())
    notify.notify(db, ids, "announcement", body.text)
    audit.record(db, admin, "notification.announcement", "", None, audience=body.audience, recipients=len(ids))
    db.commit()
    return {"recipients": len(ids)}


# ---------- audit log ----------
@router.get("/audit-logs")
def audit_logs(action: str = "", page: int = 1, per_page: int = 50, db: Session = Depends(get_db),
               _: User = Depends(require_admin)):
    per_page, page = max(1, min(per_page, 200)), max(page, 1)
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"{action.strip()[:60]}%"))
    total = _count(db, select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AuditLog.id.desc()).offset((page - 1) * per_page).limit(per_page)).all()
    return {"data": [{"id": r.id, "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id,
                      "details": r.details, "ip": r.ip, "created_at": r.created_at,
                      "actor": {"id": r.actor.id, "name": r.actor.name} if r.actor else None} for r in rows],
            "total": total, "page": page, "per_page": per_page}


# ---------- escalations & scheduled checks ----------
@router.get("/escalations")
def escalations(status: str = "open", db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.scalars(select(Escalation).where(Escalation.status == status).order_by(Escalation.id.desc())).all()
    out = []
    for e in rows:
        link, title = "", ""
        if e.project_id:
            p = db.get(Project, e.project_id)
            link, title = f"/projects/{p.id}", p.title
        elif e.period_id:
            from app.models import BillingPeriod
            bp = db.get(BillingPeriod, e.period_id)
            r = db.get(ServiceRequest, db.get(ServiceContract, bp.contract_id).request_id)
            link, title = f"/services/{r.id}", f"{r.title} – period {bp.seq}"
        out.append({"id": e.id, "kind": e.kind, "title": title, "link": link, "note": e.note, "status": e.status,
                    "resolution_note": e.resolution_note, "created_at": e.created_at})
    return out


@router.post("/escalations/{esc_id}/resolve")
def resolve_escalation(esc_id: int, body: s.EscalationResolveIn, db: Session = Depends(get_db),
                       admin: User = Depends(require_admin)):
    e = db.get(Escalation, esc_id)
    if e is None or e.status != "open":
        raise not_found("Escalation", "التصعيد")
    e.status, e.resolution_note, e.resolved_by, e.resolved_at = "resolved", body.note, admin.id, datetime.now(UTC)
    audit.record(db, admin, "escalation.resolved", "escalation", e.id, note=body.note)
    db.commit()
    return {"id": e.id, "status": e.status}


@router.post("/checks/run")
def run_checks(body: s.ChecksIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Runs the daily checks now. In demo mode an 'as of' date can be given to simulate time passing."""
    if body.as_of and not get_settings().demo_mode:
        raise bad_request("Simulated dates are available in demo mode only.", "التواريخ الافتراضية متاحة في الوضع التجريبي فقط.")
    result = checks.run(db, body.as_of)
    audit.record(db, admin, "checks.run", "", None, as_of=str(body.as_of or biz_today()), **result)
    db.commit()
    return result


@router.get("/legacy")
def legacy(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Records from the old EngConnect payment flow (kept unchanged, read-only)."""
    return {"payments": _count(db, select(func.count(Payment.id))), "withdrawals": _count(db, select(func.count(Withdrawal.id))),
            "reviews": _count(db, select(func.count(Review.id))),
            "note": "The EngConnect Stripe/escrow flow is switched off in BUNYAH. See docs/LEGACY.md."}
