"""Shared modules: simulated finance, disputes, notifications, ratings and the dashboard."""
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import schemas as s
from app.database import get_db
from app.errors import bad_request, conflict, forbidden, not_found
from app.models import (
    Dispute,
    DisputeStatus,
    Notification,
    Offer,
    OfferStatus,
    Project,
    ProjectStatus as P,
    Rating,
    RequestStatus as R,
    Role,
    ServiceApplication,
    ServiceContract,
    ServiceRequest,
    SimInvoice,
    SimTransaction,
    User,
)
from app.security import current_user, is_admin, org_context
from app.services import audit, checks, finance, notify
from app.services import disputes as D
from app.services import files as filesvc
from app.services import model_a as A
from app.services import model_b as B

router = APIRouter(tags=["shared"])


# ---------- simulated finance ----------
@router.get("/finance")
def my_finance(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Invoices and transactions for my organization (finance roles) or for me as an engineer. All DEMO."""
    if user.role == Role.ORGANIZATION:
        ctx = org_context(db, user)
        if ctx is None or not ctx.can("finance.view"):
            raise forbidden("Your role can't view financial records.", "دورك لا يسمح بعرض السجلات المالية.")
        inv_cond, tx_cond = SimInvoice.org_id == ctx.org.id, SimTransaction.org_id == ctx.org.id
    elif user.role == Role.ENGINEER:
        inv_cond, tx_cond = SimInvoice.engineer_id == user.id, SimTransaction.engineer_id == user.id
    else:
        raise forbidden()
    invs = db.scalars(select(SimInvoice).where(inv_cond).order_by(SimInvoice.id.desc()).limit(300)).all()
    txs = db.scalars(select(SimTransaction).where(tx_cond).order_by(SimTransaction.id.desc()).limit(300)).all()
    payouts = [t for t in txs if t.kind == "payout"]
    return {
        "simulated": True,
        "totals": {
            "invoiced_cents": sum(i.total_cents for i in invs),
            "paid_cents": sum(i.total_cents for i in invs if i.status == "paid"),
            "outstanding_cents": sum(i.total_cents for i in invs if i.status == "issued"),
            "refunded_cents": sum(i.total_cents for i in invs if i.status == "refunded"),
            "payouts_pending_cents": sum(t.gross_cents - t.engineer_fee_cents for t in payouts if t.status == "pending"),
            "payouts_sent_cents": sum(t.gross_cents - t.engineer_fee_cents for t in payouts if t.status == "completed"),
            "fees_cents": sum((i.org_fee_cents + i.engineer_fee_cents) for i in invs if i.status == "paid"),
        },
        "invoices": [finance.invoice_out(i) | {"title": i.description} for i in invs],
        "transactions": [finance.tx_out(t) for t in txs],
    }


@router.post("/invoices/{invoice_id}/pay")
def pay_invoice(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Records a SIMULATED payment. No money moves and no card details are collected."""
    inv = db.get(SimInvoice, invoice_id)
    ctx = org_context(db, user)
    if inv is None or ctx is None or ctx.org.id != inv.org_id:
        raise not_found("Invoice", "الفاتورة")
    ctx.require("finance.pay")
    pay, payout = finance.record_payment(db, user, inv)
    audit.record(db, user, "finance.simulated_payment", "invoice", inv.id, amount=inv.total_cents, tx=pay.ref)
    title = inv.description
    notify.notify(db, [inv.engineer_id], "payment_recorded", title, "/finance")
    db.commit()
    return {"invoice": finance.invoice_out(inv), "payment": finance.tx_out(pay), "payout": finance.tx_out(payout)}


# ---------- disputes ----------
@router.get("/disputes")
def list_disputes(db: Session = Depends(get_db), user: User = Depends(current_user)):
    if is_admin(user):
        rows = db.scalars(select(Dispute).order_by(Dispute.id.desc()).limit(300)).all()
    elif user.role == Role.ORGANIZATION:
        ctx = org_context(db, user)
        oid = ctx.org.id if ctx else -1
        rows = db.scalars(select(Dispute).outerjoin(Project, Project.id == Dispute.project_id)
                          .outerjoin(ServiceRequest, ServiceRequest.id == Dispute.request_id)
                          .where(or_(Project.org_id == oid, ServiceRequest.org_id == oid))
                          .order_by(Dispute.id.desc())).all()
    else:
        contracted = select(ServiceContract.request_id).where(ServiceContract.engineer_id == user.id)
        rows = db.scalars(select(Dispute).outerjoin(Project, Project.id == Dispute.project_id)
                          .where(or_(Project.freelancer_id == user.id, Dispute.request_id.in_(contracted)))
                          .order_by(Dispute.id.desc())).all()
    out = []
    for d in rows:
        _, side = D.get_dispute(db, d.id, user)
        out.append(D.dispute_out(db, d, side, full=False))
    return out


@router.post("/disputes", status_code=201)
def open_dispute(body: s.DisputeIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d = D.open_dispute(db, user, body.subject_type, body.subject_id, body.reason_code, body.description)
    db.commit()
    return D.dispute_out(db, d, d.raised_by_side)


@router.get("/disputes/{dispute_id}")
def get_dispute(dispute_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d, side = D.get_dispute(db, dispute_id, user)
    return D.dispute_out(db, d, side)


@router.post("/disputes/{dispute_id}/entries", status_code=201)
def add_entry(dispute_id: int, body: s.TextIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d, side = D.get_dispute(db, dispute_id, user)
    D.add_entry(db, user, d, side, body.body)
    db.commit()
    return D.dispute_out(db, d, side)


@router.post("/disputes/{dispute_id}/evidence", status_code=201)
def add_evidence(dispute_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    d, side = D.get_dispute(db, dispute_id, user)
    if d.status == DisputeStatus.CLOSED:
        raise conflict("This dispute is closed.", "هذا النزاع مغلق.")
    f = filesvc.store(db, file, user, kind="evidence", context_type="dispute", context_id=d.id)
    audit.record(db, user, "dispute.evidence_added", "dispute", d.id, file_id=f.id)
    db.commit()
    return D.dispute_out(db, d, side)


@router.post("/disputes/{dispute_id}/appeal")
def appeal(dispute_id: int, body: s.AppealIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d, side = D.get_dispute(db, dispute_id, user)
    D.appeal(db, user, d, side, body.reason)
    db.commit()
    return D.dispute_out(db, d, side)


# ---------- notifications ----------
@router.get("/notifications")
def notifications(unread_only: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    checks.run_if_due(db)
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = db.scalars(stmt.order_by(Notification.id.desc()).limit(100)).all()
    return [{"id": n.id, "kind": n.kind, "title_en": n.title_en, "title_ar": n.title_ar, "link": n.link,
             "read": n.read_at is not None, "created_at": n.created_at} for n in rows]


@router.get("/notifications/unread-count")
def unread(db: Session = Depends(get_db), user: User = Depends(current_user)):
    from app.routers.messages import unread_total
    n = db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user.id,
                                                            Notification.read_at.is_(None))) or 0
    return {"notifications": n, "messages": unread_total(db, user)}


@router.post("/notifications/{notification_id}/read", status_code=204)
def mark_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise not_found("Notification", "الإشعار")
    n.read_at = n.read_at or A.now()
    db.commit()


@router.post("/notifications/read-all", status_code=204)
def mark_all(db: Session = Depends(get_db), user: User = Depends(current_user)):
    for n in db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))):
        n.read_at = A.now()
    db.commit()


# ---------- ratings (two-way, after completion) ----------
def _rate(db: Session, user: User, *, subject_type: str, subject_id: int, org_id: int, engineer_id: int,
          side: str, rating: int, text: str, title: str, link: str, project_id=None, contract_id=None) -> dict:
    key = f"{subject_type}:{subject_id}:{side}"
    if db.scalar(select(Rating.id).where(Rating.subject_key == key)):
        raise conflict("You already rated this.", "سبق أن قيّمت هذا العمل.")
    db.add(Rating(subject_key=key, subject_type=subject_type, project_id=project_id, contract_id=contract_id,
                  reviewer_id=user.id, reviewer_side=side, org_id=org_id, engineer_id=engineer_id, rating=rating,
                  text=text))
    targets = [engineer_id] if side == "organization" else notify.org_user_ids(db, org_id, notify.MANAGERS)
    notify.notify(db, targets, "rating_received", title, link)
    db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/ratings", status_code=201)
def rate_project(project_id: int, body: s.RatingIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = A.get_access(db, project_id, user)
    if a.p.status != P.COMPLETED:
        raise conflict("Ratings open when the project is completed.", "يتاح التقييم بعد اكتمال المشروع.")
    if a.org:
        a.org.require("work.manage")
        side = "organization"
    elif a.hired:
        side = "engineer"
    else:
        raise forbidden()
    return _rate(db, user, subject_type="project", subject_id=a.p.id, org_id=a.p.org_id, engineer_id=a.p.freelancer_id,
                 side=side, rating=body.rating, text=body.text, title=a.p.title, link=f"/projects/{a.p.id}",
                 project_id=a.p.id)


@router.post("/service-requests/{request_id}/ratings", status_code=201)
def rate_contract(request_id: int, body: s.RatingIn, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    a = B.get_access(db, request_id, user)
    if a.r.status not in (R.COMPLETED, R.TERMINATED) or a.contract is None:
        raise conflict("Ratings open when the contract has ended.", "يتاح التقييم بعد انتهاء العقد.")
    if a.org:
        a.org.require("work.manage")
        side = "organization"
    elif a.contractor:
        side = "engineer"
    else:
        raise forbidden()
    return _rate(db, user, subject_type="contract", subject_id=a.contract.id, org_id=a.r.org_id,
                 engineer_id=a.contract.engineer_id, side=side, rating=body.rating, text=body.text, title=a.r.title,
                 link=f"/services/{a.r.id}", contract_id=a.contract.id)


# ---------- dashboard ----------
@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    checks.run_if_due(db)
    if user.role == Role.ORGANIZATION:
        ctx = org_context(db, user)
        if ctx is None:
            raise bad_request("Your account is not linked to an organization.", "حسابك غير مرتبط بجهة.")
        oid = ctx.org.id
        projects = db.scalars(select(Project).where(Project.org_id == oid).order_by(Project.created_at.desc())).all()
        reqs = db.scalars(select(ServiceRequest).where(ServiceRequest.org_id == oid)
                          .order_by(ServiceRequest.created_at.desc())).all()
        to_review = [p for p in projects if p.status in P.IN_REVIEW]
        from app.models import BillingPeriod
        periods = db.scalars(select(BillingPeriod).join(ServiceContract).where(
            ServiceContract.org_id == oid, BillingPeriod.status == "submitted")).all()
        new_props = db.scalar(select(func.count(Offer.id)).join(Project).where(
            Project.org_id == oid, Offer.status == OfferStatus.SUBMITTED)) or 0
        unpaid = db.scalar(select(func.count(SimInvoice.id)).where(SimInvoice.org_id == oid,
                                                                  SimInvoice.status == "issued")) or 0
        return {"role": "organization", "org_role": ctx.member.org_role,
                "organization": {"name": ctx.org.name, "verification_status": ctx.org.verification_status},
                "stats": {"projects_open": sum(p.status in P.EVALUATING for p in projects),
                          "projects_active": sum(p.status in P.ACTIVE for p in projects),
                          "projects_completed": sum(p.status == P.COMPLETED for p in projects),
                          "requests_active": sum(r.status in (R.ACTIVE, R.NEAR_EXPIRY) for r in reqs),
                          "proposals_new": new_props, "reviews_waiting": len(to_review) + len(periods),
                          "invoices_unpaid": unpaid},
                "attention": [A.project_out(db, p, brief=True) | {"review_due_date": p.review_due_date,
                                                                  "escalated": p.review_escalated_at is not None}
                              for p in to_review][:10]
                + [{"model": "B", "id": db.get(ServiceContract, bp.contract_id).request_id,
                    "title": db.get(ServiceRequest, db.get(ServiceContract, bp.contract_id).request_id).title,
                    "status": "period_submitted", "period_seq": bp.seq, "review_due_date": bp.review_due_date}
                   for bp in periods][:10],
                "projects": [A.project_out(db, p, brief=True) for p in projects[:20]],
                "requests": [B.request_out(db, r, brief=True) for r in reqs[:20]]}
    if user.role == Role.ENGINEER:
        prof = user.engineer_profile
        props = db.scalars(select(Offer).where(Offer.freelancer_id == user.id).order_by(Offer.id.desc())).all()
        apps = db.scalars(select(ServiceApplication).where(ServiceApplication.engineer_id == user.id)
                          .order_by(ServiceApplication.id.desc())).all()
        projects = db.scalars(select(Project).where(Project.freelancer_id == user.id)
                              .order_by(Project.created_at.desc())).all()
        contracts = db.scalars(select(ServiceContract).where(ServiceContract.engineer_id == user.id)).all()
        payouts = db.scalars(select(SimTransaction).where(SimTransaction.engineer_id == user.id,
                                                          SimTransaction.kind == "payout")).all()
        return {"role": "engineer",
                "verification_status": prof.verification_status if prof else "unverified",
                "stats": {"proposals_open": sum(o.status in OfferStatus.OPEN for o in props),
                          "applications_open": sum(a.status in ("submitted", "shortlisted") for a in apps),
                          "projects_active": sum(p.status in P.ACTIVE for p in projects),
                          "contracts_active": sum(db.get(ServiceRequest, c.request_id).status in R.RUNNING
                                                  for c in contracts),
                          "payouts_pending_cents": sum(t.gross_cents - t.engineer_fee_cents for t in payouts
                                                       if t.status == "pending"),
                          "payouts_sent_cents": sum(t.gross_cents - t.engineer_fee_cents for t in payouts
                                                    if t.status == "completed")},
                "projects": [A.project_out(db, p, brief=True) for p in projects[:20]],
                "contracts": [B.request_out(db, db.get(ServiceRequest, c.request_id), brief=True) for c in contracts],
                "proposals": [A.proposal_out(db, o, full=False) | {"project_status": o.project.status}
                              for o in props[:20]],
                "applications": [B.application_out(db, ap) | {"request_status": ap.request.status}
                                 for ap in apps[:20]]}
    return {"role": "admin"}
