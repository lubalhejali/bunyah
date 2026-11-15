"""Model B endpoints: short-term service requests, applications, contracts, time entries and billing periods."""
from typing import Literal

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import schemas as s
from app.database import get_db
from app.errors import forbidden, not_found
from app.models import (
    BillingPeriod,
    ProjectEvent,
    RequestStatus as R,
    Role,
    ServiceApplication,
    ServiceContract,
    ServiceRequest,
    SimInvoice,
    SimTransaction,
    TimeEntry,
    User,
)
from app.security import OrgContext, current_user, org_context, require_engineer, require_org
from app.services import finance
from app.services import model_b as B

router = APIRouter(tags=["Model B – short-term services"])


def _out(db: Session, a: B.RAccess) -> dict:
    db.refresh(a.r)
    return B.request_out(db, a.r, B.get_access(db, a.r.id, a.user))


@router.get("/service-requests")
def list_requests(scope: Literal["marketplace", "mine"] = "marketplace", q: str = "", discipline_id: int | None = None,
                  work_mode: Literal["remote", "onsite", "hybrid", ""] = "", status: str = "", page: int = 1,
                  per_page: int = 20, db: Session = Depends(get_db), user: User = Depends(current_user)):
    per_page, page = max(1, min(per_page, 50)), max(page, 1)
    stmt = select(ServiceRequest)
    if scope == "marketplace":
        stmt = stmt.where(ServiceRequest.status.in_(B.VISIBLE_TO_ALL))
    elif user.role == Role.ORGANIZATION:
        ctx = org_context(db, user)
        stmt = stmt.where(ServiceRequest.org_id == (ctx.org.id if ctx else -1))
    else:
        applied = select(ServiceApplication.request_id).where(ServiceApplication.engineer_id == user.id)
        contracted = select(ServiceContract.request_id).where(ServiceContract.engineer_id == user.id)
        stmt = stmt.where(or_(ServiceRequest.id.in_(applied), ServiceRequest.id.in_(contracted)))
    if status and scope == "mine":
        stmt = stmt.where(ServiceRequest.status == status)
    if q:
        like = f"%{q.strip()[:80]}%"
        stmt = stmt.where(or_(ServiceRequest.title.ilike(like), ServiceRequest.specialization.ilike(like),
                              ServiceRequest.location.ilike(like)))
    if discipline_id:
        stmt = stmt.where(ServiceRequest.discipline_id == discipline_id)
    if work_mode:
        stmt = stmt.where(ServiceRequest.work_mode == work_mode)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(ServiceRequest.created_at.desc()).offset((page - 1) * per_page).limit(per_page)).all()
    data = []
    for r in rows:
        a = B.RAccess(db, r, user)
        data.append(B.request_out(db, r, brief=True) | {
            "my_role": a.role, "my_application_status": a.application.status if a.application else None})
    return {"data": data, "total": total, "page": page, "per_page": per_page}


@router.post("/service-requests", status_code=201)
def create_request(body: s.RequestIn, db: Session = Depends(get_db), ctx: OrgContext = Depends(require_org)):
    r = B.create_request(db, ctx, body.model_dump())
    db.commit()
    return B.request_out(db, r, B.RAccess(db, r, ctx.user))


@router.get("/service-requests/{request_id}")
def get_request(request_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = B.get_access(db, request_id, user)
    return B.request_out(db, a.r, a)


@router.patch("/service-requests/{request_id}")
def update_request(request_id: int, body: s.RequestUpdate, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    a = B.get_access(db, request_id, user)
    B.update_request(db, a, body.model_dump(exclude_unset=True))
    db.commit()
    return _out(db, a)


@router.post("/service-requests/{request_id}/submit")
def submit_request(request_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = B.get_access(db, request_id, user)
    B.submit_request(db, a)
    db.commit()
    return _out(db, a)


@router.post("/service-requests/{request_id}/transitions")
def transition(request_id: int, body: s.RequestStep, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = B.get_access(db, request_id, user)
    B.org_step(db, a, body.to)
    db.commit()
    return _out(db, a)


@router.get("/service-requests/{request_id}/events")
def events(request_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = B.get_access(db, request_id, user)
    if a.role not in ("org", "contractor", "admin"):
        raise forbidden()
    rows = db.scalars(select(ProjectEvent).where(ProjectEvent.request_id == request_id).order_by(ProjectEvent.id)).all()
    return [{"id": e.id, "text": e.text, "text_ar": e.text_ar, "created_at": e.created_at} for e in rows]


# ---------- applications ----------
@router.get("/service-requests/{request_id}/applications")
def applications(request_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = B.get_access(db, request_id, user)
    if a.org or a.admin:
        rows = db.scalars(select(ServiceApplication).where(ServiceApplication.request_id == request_id,
                                                           ServiceApplication.status != "withdrawn")
                          .order_by(ServiceApplication.proposed_daily_rate_cents)).all()
    elif a.application:
        rows = [a.application]
    else:
        return []
    return [B.application_out(db, ap) for ap in rows]


@router.post("/service-requests/{request_id}/applications", status_code=201)
def apply(request_id: int, body: s.ApplicationIn, db: Session = Depends(get_db), eng: User = Depends(require_engineer)):
    a = B.get_access(db, request_id, eng)
    ap = B.apply(db, a, eng, body.model_dump())
    db.commit()
    return B.application_out(db, ap)


@router.get("/applications/mine")
def my_applications(db: Session = Depends(get_db), eng: User = Depends(require_engineer)):
    rows = db.scalars(select(ServiceApplication).where(ServiceApplication.engineer_id == eng.id)
                      .order_by(ServiceApplication.id.desc())).all()
    return [B.application_out(db, ap) | {"request_status": ap.request.status} for ap in rows]


def _application(db: Session, application_id: int, user: User) -> tuple[ServiceApplication, B.RAccess]:
    ap = db.get(ServiceApplication, application_id)
    if ap is None:
        raise not_found("Application", "طلب التقديم")
    a = B.get_access(db, ap.request_id, user)
    if not (a.org or a.admin or ap.engineer_id == user.id):
        raise not_found("Application", "طلب التقديم")
    return ap, a


@router.post("/applications/{application_id}/withdraw")
def withdraw(application_id: int, db: Session = Depends(get_db), eng: User = Depends(require_engineer)):
    ap, _ = _application(db, application_id, eng)
    B.withdraw_application(db, ap, eng)
    db.commit()
    return B.application_out(db, ap)


@router.post("/applications/{application_id}/decision")
def decide(application_id: int, body: s.ApplicationDecision, db: Session = Depends(get_db),
           user: User = Depends(current_user)):
    ap, a = _application(db, application_id, user)
    B.decide_application(db, a, ap, body.decision, body.note)
    db.commit()
    return _out(db, a)


@router.post("/service-requests/{request_id}/unselect")
def unselect(request_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = B.get_access(db, request_id, user)
    B.unselect(db, a)
    db.commit()
    return _out(db, a)


# ---------- contract ----------
@router.post("/service-requests/{request_id}/contract", status_code=201)
def prepare(request_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = B.get_access(db, request_id, user)
    B.prepare_contract(db, a)
    db.commit()
    return _out(db, a)


@router.patch("/service-requests/{request_id}/contract")
def edit_contract(request_id: int, body: s.ContractUpdate, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    a = B.get_access(db, request_id, user)
    B.update_contract(db, a, body.model_dump(exclude_unset=True, exclude_none=True))
    db.commit()
    return _out(db, a)


@router.post("/service-requests/{request_id}/contract/send")
def send(request_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = B.get_access(db, request_id, user)
    B.send_for_signature(db, a)
    db.commit()
    return _out(db, a)


@router.post("/service-requests/{request_id}/contract/return")
def back(request_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = B.get_access(db, request_id, user)
    B.back_to_preparation(db, a)
    db.commit()
    return _out(db, a)


@router.post("/service-requests/{request_id}/contract/sign")
def sign(request_id: int, body: s.SignIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = B.get_access(db, request_id, user)
    B.sign(db, a, body.full_name)
    db.commit()
    return _out(db, a)


@router.post("/service-requests/{request_id}/finish")
def finish(request_id: int, body: s.FinishIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = B.get_access(db, request_id, user)
    B.finish(db, a, body.outcome, body.reason)
    db.commit()
    return _out(db, a)


# ---------- time entries & billing periods ----------
@router.post("/service-requests/{request_id}/time-entries", status_code=201)
def add_entry(request_id: int, body: s.TimeEntryIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = B.get_access(db, request_id, user)
    B.save_entry(db, a, body.model_dump())
    db.commit()
    return _out(db, a)


def _entry(db: Session, entry_id: int, user: User) -> tuple[TimeEntry, B.RAccess]:
    e = db.get(TimeEntry, entry_id)
    if e is None:
        raise not_found("Time entry", "سجل الوقت")
    c = db.get(ServiceContract, e.contract_id)
    return e, B.get_access(db, c.request_id, user)


@router.patch("/time-entries/{entry_id}")
def edit_entry(entry_id: int, body: s.TimeEntryIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e, a = _entry(db, entry_id, user)
    B.save_entry(db, a, body.model_dump(), e)
    db.commit()
    return _out(db, a)


@router.delete("/time-entries/{entry_id}", status_code=204)
def delete_entry(entry_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e, a = _entry(db, entry_id, user)
    B.delete_entry(db, a, e)
    db.commit()
    return Response(status_code=204)


def _period(db: Session, period_id: int, user: User) -> tuple[BillingPeriod, B.RAccess]:
    p = db.get(BillingPeriod, period_id)
    if p is None:
        raise not_found("Billing period", "فترة الفوترة")
    c = db.get(ServiceContract, p.contract_id)
    return p, B.get_access(db, c.request_id, user)


@router.post("/billing-periods/{period_id}/submit")
def submit_period(period_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p, a = _period(db, period_id, user)
    B.submit_period(db, a, p)
    db.commit()
    return _out(db, a)


@router.post("/billing-periods/{period_id}/review")
def review_period(period_id: int, body: s.PeriodReview, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    p, a = _period(db, period_id, user)
    B.review_period(db, a, p, body.decision, body.comment)
    db.commit()
    return _out(db, a)


@router.get("/service-requests/{request_id}/finance")
def request_finance(request_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = B.get_access(db, request_id, user)
    if not (a.org or a.contractor or a.admin) or a.contract is None:
        raise forbidden()
    if a.org and not (a.org.can("finance.view") or a.org.can("work.manage")):
        raise forbidden()
    c = a.contract
    invs = db.scalars(select(SimInvoice).where(SimInvoice.contract_id == c.id).order_by(SimInvoice.id)).all()
    txs = db.scalars(select(SimTransaction).where(SimTransaction.contract_id == c.id).order_by(SimTransaction.id)).all()
    return {"simulated": True, "contract_value_cents": c.daily_rate_cents * c.working_days,
            "daily_rate_cents": c.daily_rate_cents,
            "approved_days": sum(p.approved_days for p in c.periods if p.status == "approved"),
            "invoiced_cents": sum(i.subtotal_cents for i in invs),
            "paid_cents": sum(i.subtotal_cents for i in invs if i.status == "paid"),
            "outstanding_cents": sum(i.total_cents for i in invs if i.status == "issued"),
            "fee_rule": finance.compute_fees(finance.active_rule(db, "B"), 10000)["snapshot"],
            "invoices": [finance.invoice_out(i) for i in invs], "transactions": [finance.tx_out(t) for t in txs]}


_ = R  # statuses are used by the services layer
