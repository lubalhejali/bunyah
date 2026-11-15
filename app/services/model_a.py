"""Model A – project-based engineering services. Every rule for projects, proposals, milestones, tasks and
versioned deliverables lives here, separate from Model B (services/model_b.py)."""
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import bad_request, conflict, forbidden, not_found
from app.models import (
    Comment,
    Deliverable,
    DeliverableVersion,
    Milestone,
    Offer,
    OfferStatus,
    Organization,
    Project,
    ProjectEvent,
    ProjectStatus as P,
    ProposalClarification,
    Rating,
    Role,
    SimInvoice,
    Task,
    User,
    Verification,
)
from app.security import OrgContext, is_admin, org_context
from app.services import finance, notify, states
from app.services import settings as cfg
from app.services.calendar import WorkCalendar, today as biz_today

N = notify


def now() -> datetime:
    return datetime.now(UTC)


def event(db: Session, actor: User | None, en: str, ar: str, project_id: int | None = None,
          request_id: int | None = None) -> None:
    db.add(ProjectEvent(project_id=project_id, request_id=request_id, actor_id=actor.id if actor else None,
                        text=en[:300], text_ar=ar[:300]))


def close_escalations(db: Session, actor: User, project_id: int | None = None, period_id: int | None = None) -> None:
    """When the organization finally reviews, any open review escalation is closed automatically (and recorded)."""
    from app.models import Escalation
    cond = Escalation.project_id == project_id if project_id else Escalation.period_id == period_id
    for e in db.scalars(select(Escalation).where(cond, Escalation.status == "open")).all():
        e.status, e.resolved_by, e.resolved_at = "resolved", actor.id, now()
        e.resolution_note = "Closed automatically: the organization recorded its review decision."


def lock(db: Session, project_id: int) -> Project:
    p = db.get(Project, project_id, with_for_update=True, populate_existing=True)
    if p is None:
        raise not_found("Project", "المشروع")
    return p


def move(db: Session, p: Project, new: str, actor: User | None, en: str, ar: str) -> None:
    states.check(states.PROJECT_FLOW, p.status, new)
    p.status = new
    event(db, actor, en, ar, project_id=p.id)


def link(p: Project) -> str:
    return f"/projects/{p.id}"


# ---------------------------------------------------------------- access
class Access:
    """Who the current user is for this project: org (with role), hired engineer, bidder, viewer or admin."""

    def __init__(self, db: Session, p: Project, user: User):
        self.p, self.user = p, user
        self.admin = is_admin(user)
        ctx = org_context(db, user)
        self.org: OrgContext | None = ctx if ctx and ctx.org.id == p.org_id else None
        self.hired = p.freelancer_id == user.id
        self.offer = None
        if user.role == Role.ENGINEER and not self.hired:
            self.offer = db.scalar(select(Offer).where(Offer.project_id == p.id, Offer.freelancer_id == user.id))

    @property
    def role(self) -> str:
        if self.org:
            return "org"
        if self.hired:
            return "hired"
        if self.offer:
            return "bidder"
        return "admin" if self.admin else "viewer"

    @property
    def participant(self) -> bool:
        return bool(self.org or self.hired or self.admin)

    def need(self, perm: str) -> OrgContext:
        if not self.org:
            raise forbidden("Only the organization that owns this project can do this.",
                            "هذا الإجراء متاح للجهة المالكة للمشروع فقط.")
        self.org.require(perm)
        return self.org

    def need_hired(self) -> None:
        if not self.hired:
            raise forbidden("Only the selected engineer can do this.", "هذا الإجراء متاح للمهندس المختار فقط.")


def get_access(db: Session, project_id: int, user: User) -> Access:
    p = db.get(Project, project_id)
    if p is None:
        raise not_found("Project", "المشروع")
    a = Access(db, p, user)
    if a.role == "viewer" and p.status != P.PUBLISHED:
        raise not_found("Project", "المشروع")  # private projects are not revealed
    return a


# ---------------------------------------------------------------- projects
def _validate_dates(body: dict) -> None:
    today = biz_today()
    if body.get("deadline") and body["deadline"] < today:
        raise bad_request("The target completion date can't be in the past.", "تاريخ الإنجاز لا يمكن أن يكون في الماضي.",
                          "BAD_DATE")
    pd = body.get("proposal_deadline")
    if pd and pd < today:
        raise bad_request("The proposal deadline can't be in the past.", "آخر موعد للعروض لا يمكن أن يكون في الماضي.",
                          "BAD_DATE")
    if pd and body.get("deadline") and pd > body["deadline"]:
        raise bad_request("The proposal deadline must be before the completion date.",
                          "يجب أن يكون آخر موعد للعروض قبل تاريخ الإنجاز.", "BAD_DATE")
    bmin, bmax = body.get("budget_min_cents"), body.get("max_budget_cents")
    if bmin and bmax and bmin > bmax:
        raise bad_request("The minimum budget is higher than the maximum.", "الحد الأدنى للميزانية أعلى من الحد الأقصى.")
    if body.get("work_mode") in ("onsite", "hybrid") and not body.get("location"):
        raise bad_request("Please add the location for on-site work.", "يرجى إضافة الموقع للعمل الميداني.",
                          "LOCATION_REQUIRED")


def create_project(db: Session, ctx: OrgContext, body: dict) -> Project:
    ctx.require("work.manage")
    _validate_dates(body)
    p = Project(org_id=ctx.org.id, office_id=ctx.user.id, status=P.DRAFT, **body)
    db.add(p)
    db.flush()
    event(db, ctx.user, "Project created as a draft.", "تم إنشاء المشروع كمسودة.", project_id=p.id)
    return p


def update_project(db: Session, a: Access, changes: dict) -> None:
    a.need("work.manage")
    states.require_status(a.p.status, P.DRAFT, P.PUBLISHED)
    merged = {k: getattr(a.p, k) for k in ("deadline", "proposal_deadline", "budget_min_cents", "max_budget_cents",
                                           "work_mode", "location")} | changes
    _validate_dates(merged)
    for k, v in changes.items():
        setattr(a.p, k, v)
    event(db, a.user, "Project details updated.", "تم تحديث تفاصيل المشروع.", project_id=a.p.id)


def publish(db: Session, a: Access) -> None:
    ctx = a.need("work.manage")
    if cfg.get(db, "require_org_verification") and ctx.org.verification_status != Verification.VERIFIED:
        raise conflict("Your organization must be verified before publishing. Submit verification from the "
                       "organization profile.", "يجب توثيق الجهة قبل النشر. أرسل طلب التوثيق من ملف الجهة.",
                       "VERIFICATION_REQUIRED")
    p = lock(db, a.p.id)
    if p.proposal_deadline and p.proposal_deadline < biz_today():
        raise conflict("The proposal deadline has passed. Update it before publishing.",
                       "انتهى موعد استقبال العروض. حدّثه قبل النشر.", "BAD_DATE")
    move(db, p, P.PUBLISHED, a.user, "Project published.", "تم نشر المشروع.")
    p.published_at = now()


def simple_move(db: Session, a: Access, new: str) -> None:
    """Organization-driven status steps that need no extra data."""
    a.need("work.manage")
    p = lock(db, a.p.id)
    texts = {
        P.APPLICATIONS_CLOSED: ("Proposal submissions closed.", "تم إغلاق استقبال العروض."),
        P.UNDER_EVALUATION: ("Evaluation started.", "بدأ تقييم العروض."),
        P.PUBLISHED: ("Project reopened for proposals.", "أعيد فتح المشروع لاستقبال العروض."),
        P.CANCELLED: ("Project cancelled.", "تم إلغاء المشروع."),
    }
    if new not in texts:
        raise bad_request("Unknown step.", "خطوة غير معروفة.")
    if new == P.PUBLISHED and p.proposal_deadline and p.proposal_deadline < biz_today():
        raise conflict("Move the proposal deadline to a future date first.", "يرجى تحديث آخر موعد للعروض أولاً.")
    if new == P.UNDER_EVALUATION and p.status == P.SHORTLISTED:
        pass  # going back from the shortlist is allowed by the flow
    move(db, p, new, a.user, *texts[new])
    if new == P.CANCELLED:
        open_offers = db.scalars(select(Offer).where(Offer.project_id == p.id,
                                                     Offer.status.in_(OfferStatus.OPEN + (OfferStatus.ACCEPTED,)))).all()
        for o in open_offers:
            o.status = OfferStatus.REJECTED
        # A selection made before cancelling no longer gives workspace access.
        p.freelancer_id = p.accepted_offer_id = None
        p.agreement_engineer_at = p.agreement_org_at = None
        N.notify(db, [o.freelancer_id for o in open_offers], "proposal_rejected", p.title, link(p))


# ---------------------------------------------------------------- proposals
def submit_proposal(db: Session, a: Access, eng: User, body: dict) -> Offer:
    p = a.p
    if p.status != P.PUBLISHED:
        raise conflict("This project is not accepting proposals.", "هذا المشروع لا يستقبل عروضًا حاليًا.",
                       "NOT_ACCEPTING")
    if p.proposal_deadline and biz_today() > p.proposal_deadline:
        raise conflict("The proposal deadline has passed.", "انتهى موعد تقديم العروض.", "DEADLINE_PASSED")
    prof = eng.engineer_profile
    if cfg.get(db, "require_engineer_verification") and (prof is None or prof.verification_status != Verification.VERIFIED):
        raise conflict("Your engineer profile must be verified before you can send proposals.",
                       "يجب توثيق ملفك المهني قبل تقديم العروض.", "VERIFICATION_REQUIRED")
    if body["price_cents"] > p.max_budget_cents:
        raise bad_request("Your price is above the project's maximum budget.", "سعرك أعلى من الحد الأقصى لميزانية المشروع.",
                          "PRICE_TOO_HIGH")
    if body["delivery_date"] < biz_today() or body["delivery_date"] > p.deadline:
        raise bad_request("The delivery date must be between today and the project's completion date.",
                          "يجب أن يكون تاريخ التسليم بين اليوم وتاريخ إنجاز المشروع.", "BAD_DATE")
    offer = a.offer
    if offer and offer.status not in (OfferStatus.SUBMITTED, OfferStatus.WITHDRAWN, OfferStatus.CLARIFICATION):
        raise conflict("Your proposal can no longer be changed.", "لم يعد بالإمكان تعديل عرضك.")
    new = offer is None
    if new:
        offer = Offer(project_id=p.id, freelancer_id=eng.id)
        db.add(offer)
    for k, v in body.items():
        setattr(offer, k, v)
    offer.status, offer.updated_at = OfferStatus.SUBMITTED, now()
    db.flush()
    if new:
        event(db, eng, f"New proposal from {eng.name}.", f"عرض جديد من {eng.name}.", project_id=p.id)
        N.notify(db, N.org_user_ids(db, p.org_id, N.MANAGERS), "proposal_received", p.title, link(p))
    return offer


def withdraw_proposal(db: Session, offer: Offer, eng: User) -> None:
    if offer.freelancer_id != eng.id:
        raise not_found("Proposal", "العرض")
    if offer.status not in OfferStatus.OPEN:
        raise conflict("Only proposals that are still open can be withdrawn.", "يمكن سحب العروض المفتوحة فقط.")
    offer.status = OfferStatus.WITHDRAWN


def decide_proposal(db: Session, a: Access, offer: Offer, decision: str, note: str) -> None:
    """decision: shortlist | reject | clarify"""
    a.need("work.manage")
    p = lock(db, a.p.id)
    if offer.project_id != p.id:
        raise not_found("Proposal", "العرض")
    if p.status not in P.EVALUATING:
        raise conflict("Proposals can be evaluated only before a provider is selected.",
                       "يمكن تقييم العروض قبل اختيار مقدم الخدمة فقط.", "INVALID_STATUS")
    if offer.status not in OfferStatus.OPEN:
        raise conflict("This proposal is no longer open.", "هذا العرض لم يعد مفتوحًا.")
    if decision == "shortlist":
        if p.status == P.PUBLISHED:
            raise conflict("Close proposal submissions before shortlisting.", "أغلق استقبال العروض قبل إعداد القائمة المختصرة.",
                           "INVALID_STATUS")
        offer.status = OfferStatus.SHORTLISTED
        if p.status == P.APPLICATIONS_CLOSED:
            move(db, p, P.UNDER_EVALUATION, a.user, "Evaluation started.", "بدأ تقييم العروض.")
        if p.status == P.UNDER_EVALUATION:
            move(db, p, P.SHORTLISTED, a.user, "Shortlist created.", "تم إعداد القائمة المختصرة.")
        event(db, a.user, f"Proposal from {offer.freelancer.name} shortlisted.",
              f"تمت إضافة عرض {offer.freelancer.name} إلى القائمة المختصرة.", project_id=p.id)
        N.notify(db, [offer.freelancer_id], "proposal_shortlisted", p.title, link(p))
    elif decision == "reject":
        offer.status, offer.decision_note = OfferStatus.REJECTED, note
        N.notify(db, [offer.freelancer_id], "proposal_rejected", p.title, link(p))
    elif decision == "clarify":
        if not note:
            raise bad_request("Please write your question.", "يرجى كتابة الاستفسار.", "NOTE_REQUIRED")
        db.add(ProposalClarification(offer_id=offer.id, author_id=a.user.id, body=note))
        if offer.status == OfferStatus.SUBMITTED:
            offer.status = OfferStatus.CLARIFICATION
        N.notify(db, [offer.freelancer_id], "proposal_clarification", p.title, link(p))
    else:
        raise bad_request("Unknown decision.", "قرار غير معروف.")


def answer_clarification(db: Session, offer: Offer, eng: User, body: str) -> None:
    if offer.freelancer_id != eng.id:
        raise not_found("Proposal", "العرض")
    if offer.status not in OfferStatus.OPEN:
        raise conflict("This proposal is no longer open.", "هذا العرض لم يعد مفتوحًا.")
    db.add(ProposalClarification(offer_id=offer.id, author_id=eng.id, body=body))
    if offer.status == OfferStatus.CLARIFICATION:
        offer.status = OfferStatus.SUBMITTED
    N.notify(db, N.org_user_ids(db, offer.project.org_id, N.MANAGERS), "proposal_clarified", offer.project.title,
             link(offer.project))


def accept_proposal(db: Session, a: Access, offer: Offer) -> None:
    a.need("work.manage")
    p = lock(db, a.p.id)
    if offer.project_id != p.id:
        raise not_found("Proposal", "العرض")
    if offer.status not in OfferStatus.OPEN:
        raise conflict("This proposal is no longer open.", "هذا العرض لم يعد مفتوحًا.")
    if offer.price_cents > p.max_budget_cents:
        raise conflict("This proposal is above the budget.", "هذا العرض أعلى من الميزانية.")
    move(db, p, P.PROPOSAL_ACCEPTED, a.user, f"Proposal from {offer.freelancer.name} accepted. Waiting for both "
         "parties to confirm the agreement.", f"تم قبول عرض {offer.freelancer.name}. بانتظار تأكيد الطرفين للاتفاقية.")
    offer.status = OfferStatus.ACCEPTED
    p.freelancer_id, p.accepted_offer_id = offer.freelancer_id, offer.id
    p.agreement_engineer_at = p.agreement_org_at = None
    N.notify(db, [offer.freelancer_id], "proposal_accepted", p.title, link(p))


def unselect(db: Session, a: Access) -> None:
    a.need("work.manage")
    p = lock(db, a.p.id)
    move(db, p, P.UNDER_EVALUATION, a.user, "Selection withdrawn. Evaluation continues.",
         "تم التراجع عن الاختيار. يستمر التقييم.")
    offer = db.get(Offer, p.accepted_offer_id) if p.accepted_offer_id else None
    if offer:
        offer.status = OfferStatus.SHORTLISTED
    p.freelancer_id = p.accepted_offer_id = None
    p.agreement_engineer_at = p.agreement_org_at = None


def agreement_text(db: Session, p: Project) -> dict:
    offer = db.get(Offer, p.accepted_offer_id) if p.accepted_offer_id else None
    ms = db.scalars(select(Milestone).where(Milestone.project_id == p.id).order_by(Milestone.seq)).all()
    return {
        "simulated_document": True,
        "notice_en": "Prototype agreement summary for demonstration. Not a legally reviewed contract.",
        "notice_ar": "ملخص اتفاقية تجريبي لأغراض العرض فقط، وليس عقدًا تمت مراجعته قانونيًا.",
        "organization": p.org.name if p.org else "",
        "engineer": p.freelancer.name if p.freelancer else "",
        "price_cents": offer.price_cents if offer else None,
        "delivery_date": offer.delivery_date if offer else None,
        "scope": p.scope or p.description,
        "deliverables": p.deliverables_text,
        "milestones": [{"seq": m.seq, "title": m.title, "amount_cents": m.amount_cents, "due_date": m.due_date}
                       for m in ms],
        "payment_basis_en": "Each milestone (and any final balance) is invoiced after the organization approves it. "
                            "Payments in this prototype are simulated.",
        "payment_basis_ar": "تصدر فاتورة كل مرحلة (والرصيد النهائي إن وجد) بعد اعتماد الجهة لها. المدفوعات في هذا النموذج تجريبية.",
        "engineer_accepted_at": p.agreement_engineer_at,
        "org_confirmed_at": p.agreement_org_at,
    }


def engineer_accept_agreement(db: Session, a: Access) -> None:
    a.need_hired()
    p = lock(db, a.p.id)
    states.require_status(p.status, P.PROPOSAL_ACCEPTED)
    if p.agreement_engineer_at:
        raise conflict("You already accepted the agreement.", "سبق أن وافقت على الاتفاقية.")
    p.agreement_engineer_at = now()
    event(db, a.user, "Engineer accepted the agreement.", "وافق المهندس على الاتفاقية.", project_id=p.id)
    N.notify(db, N.org_user_ids(db, p.org_id, N.MANAGERS), "agreement_accepted", p.title, link(p))


def start_work(db: Session, a: Access) -> None:
    """Organization confirms the agreement; work starts. Remaining open proposals are closed."""
    a.need("work.manage")
    p = lock(db, a.p.id)
    states.require_status(p.status, P.PROPOSAL_ACCEPTED)
    if not p.agreement_engineer_at:
        raise conflict("The engineer has not accepted the agreement yet.", "لم يوافق المهندس على الاتفاقية بعد.",
                       "AGREEMENT_PENDING")
    p.agreement_org_at = now()
    move(db, p, P.IN_PROGRESS, a.user, "Agreement confirmed by the organization. Work started.",
         "أكدت الجهة الاتفاقية. بدأ العمل.")
    others = db.scalars(select(Offer).where(Offer.project_id == p.id, Offer.status.in_(OfferStatus.OPEN))).all()
    for o in others:
        o.status = OfferStatus.REJECTED
    N.notify(db, [o.freelancer_id for o in others], "proposal_rejected", p.title, link(p))
    N.notify(db, [p.freelancer_id] + N.org_user_ids(db, p.org_id), "project_started", p.title, link(p))
    first = db.scalar(select(Milestone).where(Milestone.project_id == p.id).order_by(Milestone.seq).limit(1))
    if first and first.status == "planned":
        first.status = "in_progress"


def agreed_price(db: Session, p: Project) -> int | None:
    if not p.accepted_offer_id:
        return None
    return db.scalar(select(Offer.price_cents).where(Offer.id == p.accepted_offer_id))


# ---------------------------------------------------------------- milestones
def save_milestone(db: Session, a: Access, body: dict, milestone: Milestone | None = None) -> Milestone:
    a.need("work.manage")
    p = lock(db, a.p.id)
    states.require_status(p.status, P.PROPOSAL_ACCEPTED, P.IN_PROGRESS, P.REVISION)
    existing = db.scalars(select(Milestone).where(Milestone.project_id == p.id)).all()
    if milestone is None and len(existing) >= int(cfg.get(db, "max_milestones")):
        raise conflict(f"A project can have at most {cfg.get(db, 'max_milestones')} milestones.",
                       f"الحد الأقصى للمراحل هو {cfg.get(db, 'max_milestones')}.", "MILESTONE_LIMIT")
    if milestone is not None and milestone.status == "approved":
        raise conflict("Approved milestones can't be changed.", "لا يمكن تعديل مرحلة معتمدة.")
    others = sum(m.amount_cents for m in existing if milestone is None or m.id != milestone.id)
    price = agreed_price(db, p) or 0
    if others + body["amount_cents"] > price:
        raise bad_request("Milestone amounts add up to more than the agreed price.",
                          "مجموع مبالغ المراحل يتجاوز السعر المتفق عليه.", "OVER_PRICE")
    if milestone is None:
        milestone = Milestone(project_id=p.id, seq=(max((m.seq for m in existing), default=0) + 1))
        db.add(milestone)
        event(db, a.user, f"Milestone added: {body['title']}", f"تمت إضافة مرحلة: {body['title']}", project_id=p.id)
    for k, v in body.items():
        setattr(milestone, k, v)
    db.flush()
    return milestone


def delete_milestone(db: Session, a: Access, m: Milestone) -> None:
    a.need("work.manage")
    if m.status != "planned":
        raise conflict("Only milestones that have not started can be removed.", "يمكن حذف المراحل التي لم تبدأ فقط.")
    if db.scalar(select(Deliverable.id).where(Deliverable.milestone_id == m.id).limit(1)):
        raise conflict("Move or remove this milestone's deliverables first.", "انقل تسليمات هذه المرحلة أولاً.")
    db.delete(m)
    event(db, a.user, f"Milestone removed: {m.title}", f"تم حذف مرحلة: {m.title}", project_id=a.p.id)


def approve_milestone(db: Session, a: Access, m: Milestone) -> SimInvoice | None:
    a.need("work.manage")
    p = lock(db, a.p.id)
    states.require_status(p.status, P.IN_PROGRESS, P.SUBMITTED, P.REVISION, P.RESUBMITTED, P.APPROVED)
    if m.status == "approved":
        raise conflict("This milestone is already approved.", "هذه المرحلة معتمدة مسبقًا.")
    pending = db.scalar(select(func.count(Deliverable.id)).where(Deliverable.milestone_id == m.id,
                                                                 Deliverable.status != "approved"))
    if pending:
        raise conflict("All deliverables of this milestone must be approved first.",
                       "يجب اعتماد جميع تسليمات هذه المرحلة أولاً.", "DELIVERABLES_PENDING")
    m.status, m.approved_at = "approved", now()
    nxt = db.scalar(select(Milestone).where(Milestone.project_id == p.id, Milestone.status == "planned")
                    .order_by(Milestone.seq).limit(1))
    if nxt:
        nxt.status = "in_progress"
    event(db, a.user, f"Milestone approved: {m.title}", f"تم اعتماد المرحلة: {m.title}", project_id=p.id)
    inv = finance.issue_invoice(db, model="A", org_id=p.org_id, engineer_id=p.freelancer_id,
                                amount_cents=m.amount_cents, description=f"{p.title} – milestone {m.seq}: {m.title}",
                                project_id=p.id, milestone_id=m.id)
    N.notify(db, [p.freelancer_id], "milestone_approved", p.title, link(p))
    if inv:
        N.notify(db, N.org_user_ids(db, p.org_id, N.FINANCE), "invoice_issued", p.title, "/finance")
    return inv


# ---------------------------------------------------------------- tasks
def save_task(db: Session, a: Access, body: dict, task: Task | None = None) -> Task:
    if not (a.org and a.org.can("work.manage")) and not a.hired:
        raise forbidden()
    states.require_status(a.p.status, P.PROPOSAL_ACCEPTED, *P.WORKING)
    if body.get("milestone_id") and db.scalar(select(Milestone.project_id).where(
            Milestone.id == body["milestone_id"])) != a.p.id:
        raise bad_request("That milestone isn't part of this project.", "هذه المرحلة ليست ضمن المشروع.")
    if body.get("assignee_id") and body["assignee_id"] not in _participant_ids(db, a.p):
        raise bad_request("Tasks can be assigned only to people working on this project.",
                          "يمكن إسناد المهام للمشاركين في المشروع فقط.")
    if task is None:
        task = Task(project_id=a.p.id, created_by=a.user.id)
        db.add(task)
    for k, v in body.items():
        setattr(task, k, v)
    db.flush()
    return task


def _participant_ids(db: Session, p: Project) -> set[int]:
    return set(N.org_user_ids(db, p.org_id)) | ({p.freelancer_id} if p.freelancer_id else set())


# ---------------------------------------------------------------- deliverables & versions
def add_deliverable(db: Session, a: Access, title: str, description: str, milestone_id: int | None) -> Deliverable:
    if not (a.org and a.org.can("work.manage")) and not a.hired:
        raise forbidden()
    states.require_status(a.p.status, P.PROPOSAL_ACCEPTED, P.IN_PROGRESS, P.REVISION)
    if milestone_id and db.scalar(select(Milestone.project_id).where(Milestone.id == milestone_id)) != a.p.id:
        raise bad_request("That milestone isn't part of this project.", "هذه المرحلة ليست ضمن المشروع.")
    d = Deliverable(project_id=a.p.id, title=title, description=description, milestone_id=milestone_id,
                    created_by=a.user.id)
    db.add(d)
    db.flush()
    event(db, a.user, f"Deliverable defined: {title}", f"تم تعريف تسليم: {title}", project_id=a.p.id)
    return d


def add_version(db: Session, a: Access, d: Deliverable, file_id: int, note: str) -> DeliverableVersion:
    """A new version never replaces the old one. The previous version keeps its file and review history."""
    a.need_hired()
    p = lock(db, a.p.id)
    states.require_status(p.status, P.IN_PROGRESS, P.REVISION)
    if d.status == "approved":
        raise conflict("This deliverable is already approved.", "هذا التسليم معتمد مسبقًا.")
    last = db.scalar(select(DeliverableVersion).where(DeliverableVersion.deliverable_id == d.id)
                     .order_by(DeliverableVersion.version_no.desc()).limit(1))
    if last and last.review_status == "under_review":
        last.review_status = "superseded"   # replaced by a newer version before it was reviewed (still kept)
    v = DeliverableVersion(deliverable_id=d.id, version_no=(last.version_no + 1) if last else 1, file_id=file_id,
                           uploaded_by=a.user.id, note=note, review_status="under_review")
    db.add(v)
    d.status = "under_review"
    db.flush()
    event(db, a.user, f"{d.title}: version V{v.version_no} uploaded.", f"{d.title}: تم رفع النسخة V{v.version_no}.",
          project_id=p.id)
    N.notify(db, N.org_user_ids(db, p.org_id, N.REVIEWERS), "deliverable_uploaded", p.title, link(p))
    return v


def review_version(db: Session, a: Access, v: DeliverableVersion, decision: str, comment: str) -> None:
    a.need("work.review")
    p = lock(db, a.p.id)
    states.require_status(p.status, P.IN_PROGRESS, P.SUBMITTED, P.RESUBMITTED)
    d = v.deliverable
    if d.project_id != p.id:
        raise not_found("Version", "النسخة")
    latest = max(x.version_no for x in d.versions)
    if v.version_no != latest or v.review_status != "under_review":
        raise conflict("Only the latest version that is under review can be reviewed.",
                       "يمكن مراجعة أحدث نسخة قيد المراجعة فقط.")
    if decision == "revision_requested" and not comment:
        raise bad_request("Please explain what needs to change.", "يرجى توضيح التعديلات المطلوبة.", "NOTE_REQUIRED")
    if decision not in ("approved", "revision_requested"):
        raise bad_request("Unknown decision.", "قرار غير معروف.")
    v.review_status, v.review_comment, v.reviewed_by, v.reviewed_at = decision, comment, a.user.id, now()
    close_escalations(db, a.user, project_id=p.id)
    d.status = decision
    if comment:
        db.add(Comment(project_id=p.id, author_id=a.user.id, file_id=v.file_id, kind="technical_review",
                       body=f"[{d.title} V{v.version_no}] {comment}"))
    if decision == "approved":
        event(db, a.user, f"{d.title}: V{v.version_no} approved.", f"{d.title}: تم اعتماد النسخة V{v.version_no}.",
              project_id=p.id)
        N.notify(db, [p.freelancer_id], "version_approved", p.title, link(p))
    else:
        event(db, a.user, f"{d.title}: revision requested on V{v.version_no}.",
              f"{d.title}: طُلب تعديل على النسخة V{v.version_no}.", project_id=p.id)
        N.notify(db, [p.freelancer_id], "revision_requested", p.title, link(p))


def submit_for_review(db: Session, a: Access, note: str) -> None:
    a.need_hired()
    p = lock(db, a.p.id)
    ds = db.scalars(select(Deliverable).where(Deliverable.project_id == p.id)).all()
    if not ds:
        raise conflict("Add at least one deliverable and upload a version before submitting.",
                       "أضف تسليمًا واحدًا على الأقل وارفع نسخة قبل التقديم.", "NOTHING_TO_SUBMIT")
    waiting = [d.title for d in ds if d.status in ("awaiting_upload", "revision_requested")]
    if waiting:
        raise conflict("Upload a new version for: " + ", ".join(waiting), "ارفع نسخة جديدة لـ: " + "، ".join(waiting),
                       "VERSIONS_MISSING")
    new = P.SUBMITTED if p.status == P.IN_PROGRESS else P.RESUBMITTED
    move(db, p, new, a.user, "Work submitted for review." if new == P.SUBMITTED else "Work resubmitted for review.",
         "تم تقديم العمل للمراجعة." if new == P.SUBMITTED else "أعيد تقديم العمل للمراجعة.")
    cal = WorkCalendar.load(db)
    p.submitted_at = now()
    p.review_due_date = cal.add_working_days(biz_today(), int(cfg.get(db, "review_window_working_days")))
    p.review_reminders_sent, p.review_escalated_at = 0, None
    if note:
        db.add(Comment(project_id=p.id, author_id=a.user.id, body=note))
    N.notify(db, N.org_user_ids(db, p.org_id, N.REVIEWERS), "submitted_for_review", p.title, link(p))


def request_project_revision(db: Session, a: Access, note: str) -> None:
    a.need("work.review")
    if not note:
        raise bad_request("Please explain what needs to change.", "يرجى توضيح التعديلات المطلوبة.", "NOTE_REQUIRED")
    p = lock(db, a.p.id)
    move(db, p, P.REVISION, a.user, "Revision requested.", "طُلب تعديل.")
    close_escalations(db, a.user, project_id=p.id)
    p.review_due_date = None
    # Versions still waiting for review go back to the engineer together with the project.
    for d in db.scalars(select(Deliverable).where(Deliverable.project_id == p.id, Deliverable.status == "under_review")):
        latest = d.versions[-1] if d.versions else None
        if latest and latest.review_status == "under_review":
            latest.review_status, latest.review_comment = "revision_requested", note
            latest.reviewed_by, latest.reviewed_at = a.user.id, now()
        d.status = "revision_requested"
    db.add(Comment(project_id=p.id, author_id=a.user.id, kind="technical_review", body=note))
    N.notify(db, [p.freelancer_id], "revision_requested", p.title, link(p))


def approve_final(db: Session, a: Access) -> list[SimInvoice]:
    a.need("work.manage")
    p = lock(db, a.p.id)
    ds = db.scalars(select(Deliverable).where(Deliverable.project_id == p.id)).all()
    if not ds or any(d.status != "approved" for d in ds):
        raise conflict("Approve every deliverable before the final approval.",
                       "اعتمد جميع التسليمات قبل الاعتماد النهائي.", "DELIVERABLES_PENDING")
    move(db, p, P.APPROVED, a.user, "Final delivery approved.", "تم اعتماد التسليم النهائي.")
    p.approved_at, p.review_due_date = now(), None
    invoices = []
    for m in db.scalars(select(Milestone).where(Milestone.project_id == p.id, Milestone.status != "approved")):
        m.status, m.approved_at = "approved", now()
        inv = finance.issue_invoice(db, model="A", org_id=p.org_id, engineer_id=p.freelancer_id,
                                    amount_cents=m.amount_cents,
                                    description=f"{p.title} – milestone {m.seq}: {m.title}", project_id=p.id,
                                    milestone_id=m.id)
        invoices.append(inv)
    planned = db.scalar(select(func.coalesce(func.sum(Milestone.amount_cents), 0)).where(Milestone.project_id == p.id))
    final = (agreed_price(db, p) or 0) - int(planned or 0)
    inv = finance.issue_invoice(db, model="A", org_id=p.org_id, engineer_id=p.freelancer_id, amount_cents=final,
                                description=f"{p.title} – final payment", project_id=p.id)
    invoices.append(inv)
    N.notify(db, [p.freelancer_id], "project_approved", p.title, link(p))
    N.notify(db, N.org_user_ids(db, p.org_id, N.FINANCE), "invoice_issued", p.title, "/finance")
    return [i for i in invoices if i]


def complete(db: Session, a: Access) -> None:
    a.need("work.manage")
    p = lock(db, a.p.id)
    unpaid = db.scalar(select(func.count(SimInvoice.id)).where(SimInvoice.project_id == p.id,
                                                              SimInvoice.status == "issued"))
    if unpaid:
        raise conflict("Record the (simulated) payment of all invoices before closing the project.",
                       "سجّل الدفع التجريبي لجميع الفواتير قبل إغلاق المشروع.", "INVOICES_OPEN")
    move(db, p, P.COMPLETED, a.user, "Project completed.", "اكتمل المشروع.")
    p.completed_at = now()
    N.notify(db, [p.freelancer_id] + N.org_user_ids(db, p.org_id), "project_completed", p.title, link(p))


# ---------------------------------------------------------------- serialization
def project_out(db: Session, p: Project, a: Access | None = None, brief: bool = False) -> dict:
    org = p.org or (db.get(Organization, p.org_id) if p.org_id else None)
    out = {
        "id": p.id, "model": "A", "title": p.title, "description": p.description, "status": p.status,
        "discipline": discipline_out(p.discipline), "work_mode": p.work_mode, "location": p.location,
        "budget_min_cents": p.budget_min_cents, "max_budget_cents": p.max_budget_cents,
        "duration_days": p.duration_days, "proposal_deadline": p.proposal_deadline, "deadline": p.deadline,
        "organization": {"id": org.id, "name": org.name, "name_ar": org.name_ar,
                         "verified": org.verification_status == Verification.VERIFIED} if org else None,
        "proposal_count": db.scalar(select(func.count(Offer.id)).where(
            Offer.project_id == p.id, Offer.status != OfferStatus.WITHDRAWN)) or 0,
        "created_at": p.created_at, "published_at": p.published_at, "is_delayed": p.is_delayed,
        "is_demo": p.is_demo,
    }
    if brief:
        return out
    out |= {"scope": p.scope, "deliverables_text": p.deliverables_text, "requirements": p.requirements,
            "qualifications": p.qualifications}
    if a is None:
        return out
    out["my_role"] = a.role
    out["my_org_role"] = a.org.member.org_role if a.org else None
    if a.participant:
        price = agreed_price(db, p)
        out |= {
            "engineer": user_mini(p.freelancer) if p.freelancer else None,
            "agreed_price_cents": price, "accepted_proposal_id": p.accepted_offer_id,
            "agreement_engineer_at": p.agreement_engineer_at, "agreement_org_at": p.agreement_org_at,
            "review_due_date": p.review_due_date, "review_escalated": p.review_escalated_at is not None,
            "submitted_at": p.submitted_at, "approved_at": p.approved_at, "completed_at": p.completed_at,
            "allowed_next": sorted(states.PROJECT_FLOW.get(p.status, set())),
            "rated_by_me": _rated(db, p, a),
            "dispute_id": _latest_dispute(db, project_id=p.id),
        }
    if a.offer:
        out["my_proposal_id"] = a.offer.id
    return out


def _latest_dispute(db: Session, project_id: int | None = None, request_id: int | None = None) -> int | None:
    from app.models import Dispute
    cond = Dispute.project_id == project_id if project_id else Dispute.request_id == request_id
    return db.scalar(select(Dispute.id).where(cond).order_by(Dispute.id.desc()).limit(1))


def _rated(db: Session, p: Project, a: Access) -> bool:
    side = "organization" if a.org else "engineer"
    return db.scalar(select(Rating.id).where(Rating.subject_key == f"project:{p.id}:{side}")) is not None


def proposal_out(db: Session, o: Offer, full: bool = True) -> dict:
    eng = o.freelancer
    prof = eng.engineer_profile
    from app.services.serialize import engineer_rating
    avg, count = engineer_rating(db, eng.id)
    out = {"id": o.id, "project_id": o.project_id, "project_title": o.project.title, "status": o.status,
           "price_cents": o.price_cents, "delivery_date": o.delivery_date, "duration_days": o.duration_days,
           "summary": o.message, "technical_approach": o.technical_approach, "decision_note": o.decision_note,
           "created_at": o.created_at, "updated_at": o.updated_at,
           "engineer": user_mini(eng) | {
               "title": prof.title if prof else eng.headline,
               "years_experience": prof.years_experience if prof else 0,
               "discipline": discipline_out(prof.discipline) if prof else None,
               "verified": bool(prof and prof.verification_status == Verification.VERIFIED),
               "average_rating": avg, "rating_count": count}}
    if full:
        rows = db.scalars(select(ProposalClarification).where(ProposalClarification.offer_id == o.id)
                          .order_by(ProposalClarification.id)).all()
        out["clarifications"] = [{"id": c.id, "body": c.body, "author": user_mini(c.author),
                                  "created_at": c.created_at} for c in rows]
        from app.models import StoredFile
        files = db.scalars(select(StoredFile).where(StoredFile.context_type == "proposal",
                                                    StoredFile.context_id == o.id)).all()
        from app.services.files import file_out
        out["attachments"] = [file_out(f) for f in files]
    return out


def deliverable_out(db: Session, d: Deliverable) -> dict:
    from app.services.files import file_out
    return {"id": d.id, "title": d.title, "description": d.description, "milestone_id": d.milestone_id,
            "status": d.status, "created_at": d.created_at,
            "versions": [{"id": v.id, "version_no": v.version_no, "file": file_out(v.file), "note": v.note,
                          "uploaded_by": user_mini(v.uploader), "created_at": v.created_at,
                          "review_status": v.review_status, "review_comment": v.review_comment,
                          "reviewed_by": user_mini(v.reviewer) if v.reviewer else None, "reviewed_at": v.reviewed_at}
                         for v in d.versions]}


def user_mini(u: User | None) -> dict | None:
    if u is None:
        return None
    return {"id": u.id, "name": u.name, "role": u.role}


def discipline_out(d) -> dict | None:
    return {"id": d.id, "code": d.code, "name_en": d.name_en, "name_ar": d.name_ar} if d else None
