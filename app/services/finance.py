"""SIMULATED finance. No real money moves, no card details are collected, and BUNYAH does not hold funds.

Model used by the prototype (chosen because the custody/escrow question, Blueprint D1, is not approved):
pay on approval. When an organization approves a milestone (Model A) or a billing period (Model B), a DEMO invoice
is issued. Recording a DEMO payment against it creates a DEMO payout record for the engineer, which an administrator
marks as "simulated payout sent". Every record is stored with simulated=True and shown with a DEMO label.

The payment provider is a separate, replaceable piece: see SimulatedProvider below. A real provider would be added
as another class with the same methods once D1 is approved.
"""
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import bad_request, conflict
from app.models import (
    FeeRule,
    Milestone,
    Project,
    SimInvoice,
    SimTransaction,
    User,
)
from app.services import settings as cfg


# ---------- fees ----------
def active_rule(db: Session, model: str) -> FeeRule | None:
    return db.scalar(select(FeeRule).where(FeeRule.model == model, FeeRule.is_active.is_(True))
                     .order_by(FeeRule.id.desc()).limit(1))


def compute_fees(rule: FeeRule | None, amount_cents: int) -> dict:
    """Returns the fee for each side and a snapshot of the rule, so later rule changes never alter old records."""
    if rule is None:
        return {"org_fee_cents": 0, "engineer_fee_cents": 0,
                "snapshot": {"rule_id": None, "description": "No fee rule active"}}

    def one(value: int) -> int:
        return round(amount_cents * value / 10000) if rule.fee_type == "percent" else value

    org_fee = one(rule.org_value) if rule.payer in ("organization", "both") else 0
    eng_fee = one(rule.engineer_value) if rule.payer in ("engineer", "both") else 0
    eng_fee = min(eng_fee, amount_cents)
    return {"org_fee_cents": org_fee, "engineer_fee_cents": eng_fee,
            "snapshot": {"rule_id": rule.id, "model": rule.model, "payer": rule.payer, "fee_type": rule.fee_type,
                         "org_value": rule.org_value, "engineer_value": rule.engineer_value}}


def save_rule(db: Session, admin: User, model: str, payer: str, fee_type: str, org_value: int,
              engineer_value: int, note: str) -> FeeRule:
    if model not in ("A", "B") or payer not in ("organization", "engineer", "both") or \
            fee_type not in ("percent", "fixed"):
        raise bad_request("Invalid fee rule.", "قاعدة الرسوم غير صالحة.")
    if fee_type == "percent" and (org_value > 5000 or engineer_value > 5000):
        raise bad_request("A percentage fee can be at most 50%.", "لا يمكن أن تتجاوز النسبة 50%.")
    for r in db.scalars(select(FeeRule).where(FeeRule.model == model, FeeRule.is_active.is_(True))).all():
        r.is_active = False  # the previous rule stays in history; old records keep their snapshot
    rule = FeeRule(model=model, payer=payer, fee_type=fee_type, org_value=org_value if payer != "engineer" else 0,
                   engineer_value=engineer_value if payer != "organization" else 0, note=note, created_by=admin.id)
    db.add(rule)
    db.flush()
    return rule


# ---------- numbering ----------
def _next_number(db: Session, model_cls, column, prefix: str) -> str:
    """Sequential, readable numbers plus a short random suffix, so two simultaneous approvals never collide."""
    import secrets
    n = (db.scalar(select(func.max(model_cls.id))) or 0) + 1
    return f"{prefix}{n:05d}-{secrets.token_hex(2).upper()}"


# ---------- provider (replaceable) ----------
class SimulatedProvider:
    """Stand-in for a licensed payment provider. Always succeeds instantly and never contacts anyone."""
    name = "simulated"

    def charge(self, invoice: SimInvoice) -> str:
        return f"SIM-{invoice.number}"

    def payout(self, tx: SimTransaction) -> str:
        return f"SIM-{tx.ref}"

    def refund(self, tx: SimTransaction) -> str:
        return f"SIM-REFUND-{tx.ref}"


provider = SimulatedProvider()


# ---------- invoices & transactions ----------
def issue_invoice(db: Session, *, model: str, org_id: int, engineer_id: int, amount_cents: int, description: str,
                  project_id: int | None = None, milestone_id: int | None = None, contract_id: int | None = None,
                  period_id: int | None = None) -> SimInvoice | None:
    if amount_cents <= 0:
        return None
    fees = compute_fees(active_rule(db, model), amount_cents)
    vat_pct = float(cfg.get(db, "vat_percent"))
    vat = round((amount_cents + fees["org_fee_cents"]) * vat_pct / 100)
    inv = SimInvoice(number=_next_number(db, SimInvoice, SimInvoice.number, "DEMO-INV-"), model=model,
                     project_id=project_id, milestone_id=milestone_id, contract_id=contract_id, period_id=period_id,
                     org_id=org_id, engineer_id=engineer_id, description=description[:300],
                     subtotal_cents=amount_cents, org_fee_cents=fees["org_fee_cents"],
                     engineer_fee_cents=fees["engineer_fee_cents"], vat_percent=vat_pct, vat_cents=vat,
                     total_cents=amount_cents + fees["org_fee_cents"] + vat, fee_snapshot=fees["snapshot"])
    db.add(inv)
    db.flush()
    return inv


def _dispute_statuses(db: Session, inv: SimInvoice) -> set[str]:
    """Statuses of disputes on the project / contract this invoice belongs to."""
    from app.models import Dispute, ServiceContract
    if inv.project_id:
        stmt = select(Dispute.status).where(Dispute.project_id == inv.project_id)
    else:
        c = db.get(ServiceContract, inv.contract_id)
        stmt = select(Dispute.status).where(Dispute.request_id == c.request_id)
    return set(db.scalars(stmt).all())


def _blocked_by_dispute(db: Session, inv: SimInvoice) -> bool:
    from app.models import DisputeStatus
    return bool(_dispute_statuses(db, inv) & set(DisputeStatus.ACTIVE))


def record_payment(db: Session, actor: User, inv: SimInvoice) -> tuple[SimTransaction, SimTransaction]:
    """Organization records a SIMULATED payment of an invoice. Creates the engineer's DEMO payout record."""
    inv = db.get(SimInvoice, inv.id, with_for_update=True, populate_existing=True)
    if inv.status != "issued":
        raise conflict("This invoice is not waiting for payment.", "هذه الفاتورة ليست بانتظار الدفع.")
    if _blocked_by_dispute(db, inv):
        raise conflict("There is an open dispute. Payments wait for the administrator's decision.",
                       "يوجد نزاع مفتوح. تنتظر المدفوعات قرار الإدارة.", "DISPUTE_OPEN")
    now = datetime.now(UTC)
    common = dict(model=inv.model, project_id=inv.project_id, milestone_id=inv.milestone_id,
                  contract_id=inv.contract_id, period_id=inv.period_id, invoice_id=inv.id, org_id=inv.org_id,
                  engineer_id=inv.engineer_id, gross_cents=inv.subtotal_cents, org_fee_cents=inv.org_fee_cents,
                  engineer_fee_cents=inv.engineer_fee_cents, fee_snapshot=inv.fee_snapshot, created_by=actor.id)
    pay = SimTransaction(ref=_next_number(db, SimTransaction, SimTransaction.ref, "DEMO-TX-"), kind="payment",
                         status="completed", completed_at=now, note=f"Simulated payment of {inv.number}", **common)
    db.add(pay)
    db.flush()
    payout = SimTransaction(ref=_next_number(db, SimTransaction, SimTransaction.ref, "DEMO-TX-"), kind="payout",
                            status="pending", note=f"Simulated payout for {inv.number}", **common)
    db.add(payout)
    pay.note += f" (provider ref {provider.charge(inv)})"
    inv.status, inv.paid_at = "paid", now
    db.flush()
    return pay, payout


def mark_payout_sent(db: Session, admin: User, tx: SimTransaction) -> SimTransaction:
    if tx.kind != "payout" or tx.status != "pending":
        raise conflict("Only pending payout records can be marked as sent.", "يمكن تأكيد التحويلات المعلقة فقط.")
    tx.status, tx.completed_at = "completed", datetime.now(UTC)
    tx.note += f" – sent by admin (ref {provider.payout(tx)})"
    return tx


def record_refund(db: Session, admin: User, inv: SimInvoice, reason: str) -> SimTransaction:
    """Administrator records a SIMULATED refund of a paid invoice (e.g. after a dispute decision)."""
    if inv.status != "paid":
        raise conflict("Only paid invoices can be refunded.", "يمكن استرداد الفواتير المدفوعة فقط.")
    if _dispute_statuses(db, inv) & {"open", "under_review", "appealed"}:
        raise conflict("Record the dispute decision before any refund.",
                       "يجب تسجيل قرار النزاع قبل أي استرداد.", "DECISION_REQUIRED")
    payout = db.scalar(select(SimTransaction).where(SimTransaction.invoice_id == inv.id,
                                                    SimTransaction.kind == "payout"))
    if payout and payout.status == "pending":
        payout.status = "cancelled"
    tx = SimTransaction(ref=_next_number(db, SimTransaction, SimTransaction.ref, "DEMO-TX-"), kind="refund",
                        model=inv.model, project_id=inv.project_id, milestone_id=inv.milestone_id,
                        contract_id=inv.contract_id, period_id=inv.period_id, invoice_id=inv.id, org_id=inv.org_id,
                        engineer_id=inv.engineer_id, gross_cents=inv.subtotal_cents, org_fee_cents=inv.org_fee_cents,
                        engineer_fee_cents=inv.engineer_fee_cents, fee_snapshot=inv.fee_snapshot, status="completed",
                        completed_at=datetime.now(UTC), note=f"Simulated refund: {reason}"[:500], created_by=admin.id)
    db.add(tx)
    inv.status = "refunded"
    db.flush()
    return tx


# ---------- summaries ----------
def project_summary(db: Session, p: Project, agreed_price: int | None) -> dict:
    ms = db.scalars(select(Milestone).where(Milestone.project_id == p.id).order_by(Milestone.seq)).all()
    invs = db.scalars(select(SimInvoice).where(SimInvoice.project_id == p.id).order_by(SimInvoice.id)).all()
    txs = db.scalars(select(SimTransaction).where(SimTransaction.project_id == p.id).order_by(SimTransaction.id)).all()
    planned = sum(m.amount_cents for m in ms)
    paid = sum(i.subtotal_cents for i in invs if i.status == "paid")
    refunded = sum(i.subtotal_cents for i in invs if i.status == "refunded")
    return {
        "simulated": True,
        "agreed_price_cents": agreed_price,
        "milestones_total_cents": planned,
        "final_payment_cents": max((agreed_price or 0) - planned, 0),
        "invoiced_cents": sum(i.subtotal_cents for i in invs),
        "paid_cents": paid,
        "refunded_cents": refunded,
        "outstanding_cents": sum(i.total_cents for i in invs if i.status == "issued"),
        "fee_rule": compute_fees(active_rule(db, "A"), 10000)["snapshot"],
        "invoices": [invoice_out(i) for i in invs],
        "transactions": [tx_out(t) for t in txs],
    }


def invoice_out(i: SimInvoice) -> dict:
    return {"id": i.id, "number": i.number, "model": i.model, "description": i.description,
            "project_id": i.project_id, "contract_id": i.contract_id, "milestone_id": i.milestone_id,
            "period_id": i.period_id, "subtotal_cents": i.subtotal_cents, "org_fee_cents": i.org_fee_cents,
            "engineer_fee_cents": i.engineer_fee_cents, "vat_percent": i.vat_percent, "vat_cents": i.vat_cents,
            "total_cents": i.total_cents, "engineer_net_cents": i.subtotal_cents - i.engineer_fee_cents,
            "status": i.status, "issued_at": i.issued_at, "paid_at": i.paid_at, "simulated": True,
            "org_id": i.org_id, "engineer_id": i.engineer_id}


def tx_out(t: SimTransaction) -> dict:
    return {"id": t.id, "ref": t.ref, "kind": t.kind, "model": t.model, "project_id": t.project_id,
            "contract_id": t.contract_id, "invoice_id": t.invoice_id, "gross_cents": t.gross_cents,
            "org_fee_cents": t.org_fee_cents, "engineer_fee_cents": t.engineer_fee_cents,
            "engineer_net_cents": t.gross_cents - t.engineer_fee_cents, "status": t.status, "note": t.note,
            "created_at": t.created_at, "completed_at": t.completed_at, "simulated": True,
            "org_id": t.org_id, "engineer_id": t.engineer_id}


def rule_out(r: FeeRule) -> dict:
    return {"id": r.id, "model": r.model, "payer": r.payer, "fee_type": r.fee_type, "org_value": r.org_value,
            "engineer_value": r.engineer_value, "is_active": r.is_active, "note": r.note, "created_at": r.created_at}
