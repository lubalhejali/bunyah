"""Model B – short-term engineering service contracts (daily rate, billing periods of N working days).
Kept fully separate from Model A: own tables, own statuses, own pricing and billing rules.

The maximum contract length (default 90 working days) is a configurable setting and is NOT legally approved
(Blueprint decision D6). Use demo data only.
"""
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import bad_request, conflict, forbidden, not_found
from app.models import (
    BillingPeriod,
    Rating,
    RequestStatus as R,
    Role,
    ServiceApplication,
    ServiceContract,
    ServiceRequest,
    SimInvoice,
    TimeEntry,
    User,
    Verification,
)
from app.security import OrgContext, is_admin, org_context
from app.services import finance, notify, states
from app.services import settings as cfg
from app.services.calendar import WorkCalendar, today as biz_today
from app.services.model_a import discipline_out, event, user_mini

N = notify


def now() -> datetime:
    return datetime.now(UTC)


def link(r: ServiceRequest) -> str:
    return f"/services/{r.id}"


def lock(db: Session, request_id: int) -> ServiceRequest:
    r = db.get(ServiceRequest, request_id, with_for_update=True, populate_existing=True)
    if r is None:
        raise not_found("Service request", "طلب الخدمة")
    return r


def move(db: Session, r: ServiceRequest, new: str, actor: User | None, en: str, ar: str) -> None:
    states.check(states.REQUEST_FLOW, r.status, new)
    r.status = new
    event(db, actor, en, ar, request_id=r.id)


class RAccess:
    def __init__(self, db: Session, r: ServiceRequest, user: User):
        self.r, self.user = r, user
        self.admin = is_admin(user)
        ctx = org_context(db, user)
        self.org: OrgContext | None = ctx if ctx and ctx.org.id == r.org_id else None
        self.application = None
        if user.role == Role.ENGINEER:
            self.application = db.scalar(select(ServiceApplication).where(
                ServiceApplication.request_id == r.id, ServiceApplication.engineer_id == user.id))
        self.contract = db.scalar(select(ServiceContract).where(ServiceContract.request_id == r.id))
        self.contractor = bool(self.contract and self.contract.engineer_id == user.id)

    @property
    def role(self) -> str:
        if self.org:
            return "org"
        if self.contractor:
            return "contractor"
        if self.application:
            return "applicant"
        return "admin" if self.admin else "viewer"

    def need(self, perm: str) -> OrgContext:
        if not self.org:
            raise forbidden("Only the organization that owns this request can do this.",
                            "هذا الإجراء متاح للجهة المالكة للطلب فقط.")
        self.org.require(perm)
        return self.org

    def need_contractor(self) -> None:
        if not self.contractor:
            raise forbidden("Only the contracted engineer can do this.", "هذا الإجراء متاح للمهندس المتعاقد فقط.")


VISIBLE_TO_ALL = (R.PUBLISHED, R.APPLICATIONS_OPEN)


def get_access(db: Session, request_id: int, user: User) -> RAccess:
    r = db.get(ServiceRequest, request_id)
    if r is None:
        raise not_found("Service request", "طلب الخدمة")
    a = RAccess(db, r, user)
    if a.role == "viewer" and r.status not in VISIBLE_TO_ALL:
        raise not_found("Service request", "طلب الخدمة")
    return a


# ---------------------------------------------------------------- requests
def _validate(db: Session, body: dict) -> None:
    max_days = int(cfg.get(db, "model_b_max_working_days"))
    if body["duration_working_days"] > max_days:
        raise bad_request(f"The contract length can be at most {max_days} working days (prototype setting, "
                          "pending legal review).", f"الحد الأقصى لمدة العقد {max_days} يوم عمل (إعداد تجريبي بانتظار "
                          "المراجعة القانونية).", "DURATION_LIMIT")
    if body["start_date"] < biz_today():
        raise bad_request("The start date can't be in the past.", "تاريخ البدء لا يمكن أن يكون في الماضي.", "BAD_DATE")
    if body.get("work_mode") in ("onsite", "hybrid") and not body.get("location"):
        raise bad_request("Please add the work location.", "يرجى إضافة موقع العمل.", "LOCATION_REQUIRED")


def create_request(db: Session, ctx: OrgContext, body: dict) -> ServiceRequest:
    ctx.require("work.manage")
    _validate(db, body)
    r = ServiceRequest(org_id=ctx.org.id, created_by=ctx.user.id, status=R.DRAFT, **body)
    db.add(r)
    db.flush()
    event(db, ctx.user, "Service request created as a draft.", "تم إنشاء طلب الخدمة كمسودة.", request_id=r.id)
    return r


def update_request(db: Session, a: RAccess, changes: dict) -> None:
    a.need("work.manage")
    states.require_status(a.r.status, R.DRAFT)
    merged = {k: getattr(a.r, k) for k in ("duration_working_days", "start_date", "work_mode", "location")} | changes
    _validate(db, merged)
    for k, v in changes.items():
        setattr(a.r, k, v)
    event(db, a.user, "Request details updated.", "تم تحديث تفاصيل الطلب.", request_id=a.r.id)


def submit_request(db: Session, a: RAccess) -> None:
    ctx = a.need("work.manage")
    if cfg.get(db, "require_org_verification") and ctx.org.verification_status != Verification.VERIFIED:
        raise conflict("Your organization must be verified before submitting requests.",
                       "يجب توثيق الجهة قبل تقديم الطلبات.", "VERIFICATION_REQUIRED")
    r = lock(db, a.r.id)
    _validate(db, {k: getattr(r, k) for k in ("duration_working_days", "start_date", "work_mode", "location")})
    move(db, r, R.SUBMITTED, a.user, "Request submitted to BUNYAH for review.", "تم تقديم الطلب لمراجعة بُنية.")
    if not cfg.get(db, "require_request_review"):
        move(db, r, R.PENDING_REVIEW, None, "Automatic review (setting).", "مراجعة تلقائية (حسب الإعدادات).")
        move(db, r, R.PUBLISHED, None, "Request published.", "تم نشر الطلب.")
        r.published_at = now()
        return
    N.notify(db, N.admin_user_ids(db), "request_submitted", r.title, "/admin/requests")


def admin_review(db: Session, admin: User, r: ServiceRequest, decision: str, note: str) -> None:
    """decision: start | publish | return"""
    r = lock(db, r.id)
    if decision == "start":
        move(db, r, R.PENDING_REVIEW, admin, "BUNYAH review started.", "بدأت مراجعة بُنية.")
    elif decision == "publish":
        if r.status == R.SUBMITTED:
            move(db, r, R.PENDING_REVIEW, admin, "BUNYAH review started.", "بدأت مراجعة بُنية.")
        move(db, r, R.PUBLISHED, admin, "Approved and published by BUNYAH.", "تمت الموافقة والنشر من بُنية.")
        r.published_at, r.review_note = now(), note
        N.notify(db, N.org_user_ids(db, r.org_id, N.MANAGERS), "request_published", r.title, link(r))
    elif decision == "return":
        if not note:
            raise bad_request("Please explain what needs to change.", "يرجى توضيح التعديلات المطلوبة.", "NOTE_REQUIRED")
        if r.status == R.SUBMITTED:
            move(db, r, R.PENDING_REVIEW, admin, "BUNYAH review started.", "بدأت مراجعة بُنية.")
        move(db, r, R.DRAFT, admin, f"Returned for changes: {note}", f"أعيد للتعديل: {note}")
        r.review_note = note
        N.notify(db, N.org_user_ids(db, r.org_id, N.MANAGERS), "request_returned", r.title, link(r))
    else:
        raise bad_request("Unknown decision.", "قرار غير معروف.")


def org_step(db: Session, a: RAccess, new: str) -> None:
    a.need("work.manage")
    r = lock(db, a.r.id)
    texts = {
        R.APPLICATIONS_OPEN: ("Applications opened.", "تم فتح التقديم."),
        R.UNDER_EVALUATION: ("Applications closed. Evaluation started.", "أُغلق التقديم وبدأ التقييم."),
        R.CANCELLED: ("Request cancelled.", "تم إلغاء الطلب."),
    }
    if new not in texts:
        raise bad_request("Unknown step.", "خطوة غير معروفة.")
    move(db, r, new, a.user, *texts[new])
    if new == R.CANCELLED:
        apps = db.scalars(select(ServiceApplication).where(ServiceApplication.request_id == r.id,
                                                           ServiceApplication.status.in_(("submitted", "shortlisted",
                                                                                          "selected")))).all()
        for ap in apps:
            ap.status = "rejected"
        N.notify(db, [ap.engineer_id for ap in apps], "application_rejected", r.title, link(r))


# ---------------------------------------------------------------- applications
def apply(db: Session, a: RAccess, eng: User, body: dict) -> ServiceApplication:
    r = a.r
    if r.status != R.APPLICATIONS_OPEN:
        raise conflict("This request is not accepting applications.", "هذا الطلب لا يستقبل طلبات تقديم حاليًا.",
                       "NOT_ACCEPTING")
    prof = eng.engineer_profile
    if cfg.get(db, "require_engineer_verification") and (prof is None or prof.verification_status != Verification.VERIFIED):
        raise conflict("Your engineer profile must be verified before you can apply.",
                       "يجب توثيق ملفك المهني قبل التقديم.", "VERIFICATION_REQUIRED")
    if a.application and a.application.status != "withdrawn":
        raise conflict("You already applied to this request.", "سبق أن تقدمت على هذا الطلب.")
    ap = a.application or ServiceApplication(request_id=r.id, engineer_id=eng.id)
    for k, v in body.items():
        setattr(ap, k, v)
    ap.status = "submitted"
    db.add(ap)
    db.flush()
    event(db, eng, f"New application from {eng.name}.", f"طلب تقديم جديد من {eng.name}.", request_id=r.id)
    N.notify(db, N.org_user_ids(db, r.org_id, N.MANAGERS), "application_received", r.title, link(r))
    return ap


def withdraw_application(db: Session, ap: ServiceApplication, eng: User) -> None:
    if ap.engineer_id != eng.id:
        raise not_found("Application", "طلب التقديم")
    if ap.status not in ("submitted", "shortlisted"):
        raise conflict("Only open applications can be withdrawn.", "يمكن سحب الطلبات المفتوحة فقط.")
    ap.status = "withdrawn"


def decide_application(db: Session, a: RAccess, ap: ServiceApplication, decision: str, note: str) -> None:
    a.need("work.manage")
    r = lock(db, a.r.id)
    if ap.request_id != r.id:
        raise not_found("Application", "طلب التقديم")
    if ap.status not in ("submitted", "shortlisted"):
        raise conflict("This application is no longer open.", "طلب التقديم هذا لم يعد مفتوحًا.")
    if decision == "shortlist":
        states.require_status(r.status, R.APPLICATIONS_OPEN, R.UNDER_EVALUATION)
        ap.status = "shortlisted"
        N.notify(db, [ap.engineer_id], "application_shortlisted", r.title, link(r))
    elif decision == "reject":
        ap.status, ap.decision_note = "rejected", note
        N.notify(db, [ap.engineer_id], "application_rejected", r.title, link(r))
    elif decision == "select":
        move(db, r, R.SELECTED, a.user, f"{ap.engineer.name} selected.", f"تم اختيار {ap.engineer.name}.")
        ap.status = "selected"
        r.selected_application_id = ap.id
        N.notify(db, [ap.engineer_id], "application_selected", r.title, link(r))
    else:
        raise bad_request("Unknown decision.", "قرار غير معروف.")


def unselect(db: Session, a: RAccess) -> None:
    a.need("work.manage")
    r = lock(db, a.r.id)
    contract = a.contract
    if contract and (contract.org_signed_at or contract.engineer_signed_at):
        raise conflict("The contract has signatures. Return it to preparation first.",
                       "العقد موقّع جزئيًا. أعده لمرحلة الإعداد أولاً.")
    move(db, r, R.UNDER_EVALUATION, a.user, "Selection withdrawn.", "تم التراجع عن الاختيار.")
    ap = db.get(ServiceApplication, r.selected_application_id) if r.selected_application_id else None
    if ap:
        ap.status = "shortlisted"
    r.selected_application_id = None
    if contract:
        db.delete(contract)


# ---------------------------------------------------------------- contract
def default_terms(r: ServiceRequest) -> str:
    return ("PROTOTYPE CONTRACT TEMPLATE – NOT LEGALLY REVIEWED.\n"
            "1. The engineer provides the engineering services described in the request as an independent "
            "service provider.\n2. Fees are calculated as the agreed daily rate multiplied by the working days "
            "approved by the organization in each billing period.\n3. Each billing period is reviewed within the "
            "review window. Approval is never automatic; unresolved reviews are escalated to BUNYAH.\n"
            "4. Either party may end the contract early with written reasons recorded on the platform.\n"
            "5. Disputes follow the BUNYAH dispute process.\n\n"
            "نموذج عقد تجريبي – لم تتم مراجعته قانونيًا. تُحسب الأتعاب بضرب السعر اليومي في أيام العمل المعتمدة "
            "في كل فترة فوترة، ولا يتم أي اعتماد تلقائي.")


def prepare_contract(db: Session, a: RAccess) -> ServiceContract:
    a.need("work.manage")
    r = lock(db, a.r.id)
    move(db, r, R.CONTRACT_PREPARATION, a.user, "Contract preparation started.", "بدأ إعداد العقد.")
    ap = db.get(ServiceApplication, r.selected_application_id)
    cal = WorkCalendar.load(db)
    start = cal.next_working_day(max(r.start_date, biz_today()))
    c = a.contract
    if c is None:
        c = ServiceContract(request_id=r.id, org_id=r.org_id, engineer_id=ap.engineer_id, application_id=ap.id)
        db.add(c)
    c.start_date, c.working_days = start, r.duration_working_days
    c.end_date = cal.nth_working_day(start, r.duration_working_days)
    c.daily_rate_cents, c.hours_per_day = ap.proposed_daily_rate_cents, r.hours_per_day
    c.period_length_days = int(cfg.get(db, "billing_period_working_days"))
    c.terms = c.terms or default_terms(r)
    db.flush()
    return c


def update_contract(db: Session, a: RAccess, body: dict) -> ServiceContract:
    a.need("work.manage")
    states.require_status(a.r.status, R.CONTRACT_PREPARATION)
    c = a.contract
    max_days = int(cfg.get(db, "model_b_max_working_days"))
    days = body.get("working_days", c.working_days)
    if days > max_days:
        raise bad_request(f"The contract can be at most {max_days} working days (prototype setting, pending legal "
                          "review).", f"الحد الأقصى لمدة العقد {max_days} يوم عمل (إعداد تجريبي بانتظار المراجعة القانونية).",
                          "DURATION_LIMIT")
    start = body.get("start_date", c.start_date)
    if start < biz_today():
        raise bad_request("The start date can't be in the past.", "تاريخ البدء لا يمكن أن يكون في الماضي.", "BAD_DATE")
    for k, v in body.items():
        setattr(c, k, v)
    cal = WorkCalendar.load(db)
    c.start_date = cal.next_working_day(start)
    c.end_date = cal.nth_working_day(c.start_date, c.working_days)
    return c


def send_for_signature(db: Session, a: RAccess) -> None:
    a.need("work.manage")
    r = lock(db, a.r.id)
    move(db, r, R.AWAITING_SIGNATURES, a.user, "Contract sent for signature.", "تم إرسال العقد للتوقيع.")
    N.notify(db, [a.contract.engineer_id] + N.org_user_ids(db, r.org_id, ("owner",)), "contract_ready", r.title, link(r))


def back_to_preparation(db: Session, a: RAccess) -> None:
    a.need("work.manage")
    r = lock(db, a.r.id)
    move(db, r, R.CONTRACT_PREPARATION, a.user, "Contract returned to preparation; signatures cleared.",
         "أعيد العقد لمرحلة الإعداد وأُلغيت التواقيع.")
    c = a.contract
    c.org_signed_at = c.engineer_signed_at = None
    c.org_signed_by, c.org_signature_name, c.engineer_signature_name = None, "", ""


def sign(db: Session, a: RAccess, typed_name: str) -> None:
    """Simulated electronic signature: the signer types their full name. Not a legally valid e-signature."""
    r = lock(db, a.r.id)
    states.require_status(r.status, R.AWAITING_SIGNATURES)
    c = a.contract
    if not typed_name or typed_name.strip().casefold() != a.user.name.strip().casefold():
        raise bad_request("Type your full name exactly as it appears on your account to sign.",
                          "اكتب اسمك الكامل كما يظهر في حسابك للتوقيع.", "SIGNATURE_NAME")
    if a.org:
        a.org.require("contract.sign")
        if c.org_signed_at:
            raise conflict("The organization already signed.", "وقّعت الجهة مسبقًا.")
        c.org_signed_by, c.org_signature_name, c.org_signed_at = a.user.id, typed_name, now()
        event(db, a.user, "Contract signed by the organization.", "وقّعت الجهة العقد.", request_id=r.id)
        N.notify(db, [c.engineer_id], "contract_signed", r.title, link(r))
    elif a.contractor:
        if c.engineer_signed_at:
            raise conflict("You already signed.", "سبق أن وقّعت.")
        c.engineer_signature_name, c.engineer_signed_at = typed_name, now()
        event(db, a.user, "Contract signed by the engineer.", "وقّع المهندس العقد.", request_id=r.id)
        N.notify(db, N.org_user_ids(db, r.org_id, N.MANAGERS), "contract_signed", r.title, link(r))
    else:
        raise forbidden()
    if c.org_signed_at and c.engineer_signed_at:
        _activate(db, r, c)


def _activate(db: Session, r: ServiceRequest, c: ServiceContract) -> None:
    cal = WorkCalendar.load(db)
    if c.start_date < biz_today():  # signed late: the contract starts on the next working day
        c.start_date = cal.next_working_day(biz_today())
        c.end_date = cal.nth_working_day(c.start_date, c.working_days)
    for i, (s, e, n) in enumerate(cal.split_periods(c.start_date, c.working_days, c.period_length_days), start=1):
        db.add(BillingPeriod(contract_id=c.id, seq=i, start_date=s, end_date=e, working_days=n))
    move(db, r, R.ACTIVE, None, "Both parties signed. Contract is active.", "وقّع الطرفان. العقد ساري.")
    N.notify(db, [c.engineer_id] + N.org_user_ids(db, r.org_id), "contract_active", r.title, link(r))


# ---------------------------------------------------------------- time entries & billing periods
def _period_for(db: Session, c: ServiceContract, d: date) -> BillingPeriod | None:
    return db.scalar(select(BillingPeriod).where(BillingPeriod.contract_id == c.id, BillingPeriod.start_date <= d,
                                                 BillingPeriod.end_date >= d))


def save_entry(db: Session, a: RAccess, body: dict, entry: TimeEntry | None = None) -> TimeEntry:
    a.need_contractor()
    states.require_status(a.r.status, *R.RUNNING)
    c = a.contract
    d = body["work_date"]
    cal = WorkCalendar.load(db)
    if d > biz_today():
        raise bad_request("You can't record future days.", "لا يمكن تسجيل أيام مستقبلية.", "BAD_DATE")
    if not (c.start_date <= d <= c.end_date) or not cal.is_working_day(d):
        raise bad_request("Choose a working day inside the contract period.", "اختر يوم عمل ضمن مدة العقد.", "BAD_DATE")
    period = _period_for(db, c, d)
    if period is None or period.status not in ("open", "revision_requested"):
        raise conflict("That billing period is already submitted or approved.", "فترة الفوترة هذه مقدمة أو معتمدة.",
                       "PERIOD_LOCKED")
    if entry is None:
        if db.scalar(select(TimeEntry.id).where(TimeEntry.contract_id == c.id, TimeEntry.work_date == d)):
            raise conflict("You already recorded this day. Edit the existing entry.", "سبق تسجيل هذا اليوم. عدّل السجل الحالي.")
        entry = TimeEntry(contract_id=c.id)
        db.add(entry)
    elif entry.period_id != period.id and entry.period_id is not None:
        old = db.get(BillingPeriod, entry.period_id)
        if old.status not in ("open", "revision_requested"):
            raise conflict("That entry belongs to a locked billing period.", "هذا السجل ضمن فترة مقفلة.", "PERIOD_LOCKED")
    if body["day_fraction"] not in (0.5, 1.0):
        raise bad_request("Choose a full day or a half day.", "اختر يومًا كاملًا أو نصف يوم.")
    for k, v in body.items():
        setattr(entry, k, v)
    entry.period_id, entry.status = period.id, "recorded"
    db.flush()
    return entry


def delete_entry(db: Session, a: RAccess, entry: TimeEntry) -> None:
    a.need_contractor()
    period = db.get(BillingPeriod, entry.period_id)
    if period.status not in ("open", "revision_requested"):
        raise conflict("That entry belongs to a locked billing period.", "هذا السجل ضمن فترة مقفلة.", "PERIOD_LOCKED")
    db.delete(entry)


def submit_period(db: Session, a: RAccess, period: BillingPeriod) -> None:
    a.need_contractor()
    r = lock(db, a.r.id)
    states.require_status(r.status, *R.RUNNING, R.TERMINATED)
    if period.contract_id != a.contract.id:
        raise not_found("Billing period", "فترة الفوترة")
    if period.status not in ("open", "revision_requested"):
        raise conflict("This period is not open.", "هذه الفترة غير مفتوحة.")
    if not db.scalar(select(func.count(TimeEntry.id)).where(TimeEntry.period_id == period.id)):
        raise conflict("Record at least one working day before submitting.", "سجّل يوم عمل واحدًا على الأقل قبل التقديم.",
                       "NO_ENTRIES")
    cal = WorkCalendar.load(db)
    period.status, period.submitted_at = "submitted", now()
    period.review_due_date = cal.add_working_days(biz_today(), int(cfg.get(db, "review_window_working_days")))
    period.review_reminders_sent, period.review_escalated_at = 0, None
    event(db, a.user, f"Billing period {period.seq} submitted for approval.", f"تم تقديم فترة الفوترة {period.seq} للاعتماد.",
          request_id=r.id)
    N.notify(db, N.org_user_ids(db, r.org_id, N.MANAGERS), "period_submitted", r.title, link(r))


def review_period(db: Session, a: RAccess, period: BillingPeriod, decision: str, comment: str) -> SimInvoice | None:
    a.need("billing.approve")
    r = lock(db, a.r.id)
    if period.contract_id != a.contract.id:
        raise not_found("Billing period", "فترة الفوترة")
    if period.status != "submitted":
        raise conflict("This period is not waiting for approval.", "هذه الفترة ليست بانتظار الاعتماد.")
    if r.status == R.DISPUTED:
        raise conflict("Billing is paused while a dispute is open.", "الفوترة متوقفة أثناء وجود نزاع.", "DISPUTE_OPEN")
    entries = db.scalars(select(TimeEntry).where(TimeEntry.period_id == period.id)).all()
    c = a.contract
    from app.services.model_a import close_escalations
    close_escalations(db, a.user, period_id=period.id)
    if decision == "approve":
        days = sum(e.day_fraction for e in entries)
        period.status, period.approved_days = "approved", days
        period.amount_cents = round(c.daily_rate_cents * days)
        period.approved_by, period.approved_at, period.review_comment = a.user.id, now(), comment
        for e in entries:
            e.status = "approved"
        event(db, a.user, f"Billing period {period.seq} approved: {days:g} days.",
              f"تم اعتماد فترة الفوترة {period.seq}: {days:g} يوم.", request_id=r.id)
        inv = finance.issue_invoice(db, model="B", org_id=r.org_id, engineer_id=c.engineer_id,
                                    amount_cents=period.amount_cents,
                                    description=f"{r.title} – billing period {period.seq} ({days:g} days)",
                                    contract_id=c.id, period_id=period.id)
        N.notify(db, [c.engineer_id], "period_approved", r.title, link(r))
        N.notify(db, N.org_user_ids(db, r.org_id, N.FINANCE), "invoice_issued", r.title, "/finance")
        return inv
    if decision == "revision":
        if not comment:
            raise bad_request("Please explain what needs to change.", "يرجى توضيح التعديلات المطلوبة.", "NOTE_REQUIRED")
        period.status, period.review_comment, period.review_due_date = "revision_requested", comment, None
        event(db, a.user, f"Changes requested on billing period {period.seq}.",
              f"طُلبت تعديلات على فترة الفوترة {period.seq}.", request_id=r.id)
        N.notify(db, [c.engineer_id], "period_revision", r.title, link(r))
        return None
    raise bad_request("Unknown decision.", "قرار غير معروف.")


def finish(db: Session, a: RAccess, outcome: str, reason: str) -> None:
    """outcome: completed (organization) | terminated (either party, reason required)."""
    r = lock(db, a.r.id)
    c = a.contract
    if outcome == "completed":
        a.need("work.manage")
        open_periods = [p.seq for p in c.periods if p.status != "approved" and
                        db.scalar(select(func.count(TimeEntry.id)).where(TimeEntry.period_id == p.id))]
        if open_periods:
            raise conflict("Approve all billing periods with recorded days first.",
                           "اعتمد جميع فترات الفوترة التي تحتوي على أيام مسجلة أولاً.", "PERIODS_OPEN")
        move(db, r, R.COMPLETED, a.user, "Contract completed.", "اكتمل العقد.")
    elif outcome == "terminated":
        if a.org:
            a.org.require("work.manage")
        elif not a.contractor:
            raise forbidden()
        if not reason:
            raise bad_request("Please give the reason for ending the contract early.", "يرجى ذكر سبب إنهاء العقد مبكرًا.",
                              "NOTE_REQUIRED")
        move(db, r, R.TERMINATED, a.user, f"Contract ended early: {reason}", f"تم إنهاء العقد مبكرًا: {reason}")
    else:
        raise bad_request("Unknown outcome.", "نتيجة غير معروفة.")
    c.ended_reason, c.ended_at = reason, now()
    N.notify(db, [c.engineer_id] + N.org_user_ids(db, r.org_id), "contract_ended", r.title, link(r))


# ---------------------------------------------------------------- serialization
def request_out(db: Session, r: ServiceRequest, a: RAccess | None = None, brief: bool = False) -> dict:
    org = r.org
    out = {"id": r.id, "model": "B", "title": r.title, "status": r.status, "discipline": discipline_out(r.discipline),
           "specialization": r.specialization, "duration_working_days": r.duration_working_days,
           "hours_per_day": r.hours_per_day, "daily_rate_cents": r.daily_rate_cents, "work_mode": r.work_mode,
           "location": r.location, "start_date": r.start_date, "min_experience_years": r.min_experience_years,
           "organization": {"id": org.id, "name": org.name, "name_ar": org.name_ar,
                            "verified": org.verification_status == Verification.VERIFIED},
           "application_count": db.scalar(select(func.count(ServiceApplication.id)).where(
               ServiceApplication.request_id == r.id, ServiceApplication.status != "withdrawn")) or 0,
           "created_at": r.created_at, "published_at": r.published_at, "is_demo": r.is_demo,
           "estimated_total_cents": r.daily_rate_cents * r.duration_working_days}
    if brief:
        return out
    out |= {"qualifications": r.qualifications, "responsibilities": r.responsibilities, "outputs": r.outputs}
    if a is None:
        return out
    out["my_role"] = a.role
    out["my_org_role"] = a.org.member.org_role if a.org else None
    if a.org or a.admin:
        out["review_note"] = r.review_note
        out["allowed_next"] = sorted(states.REQUEST_FLOW.get(r.status, set()))
    if a.application:
        out["my_application"] = application_out(db, a.application)
    if a.contract and (a.org or a.contractor or a.admin):
        out["contract"] = contract_out(db, a.contract)
        side = "organization" if a.org else "engineer"
        out["rated_by_me"] = db.scalar(select(Rating.id).where(
            Rating.subject_key == f"contract:{a.contract.id}:{side}")) is not None
        from app.services.model_a import _latest_dispute
        out["dispute_id"] = _latest_dispute(db, request_id=r.id)
    return out


def application_out(db: Session, ap: ServiceApplication) -> dict:
    eng = ap.engineer
    prof = eng.engineer_profile
    from app.services.serialize import engineer_rating
    avg, count = engineer_rating(db, eng.id)
    return {"id": ap.id, "request_id": ap.request_id, "request_title": ap.request.title, "status": ap.status,
            "cover_letter": ap.cover_letter, "proposed_daily_rate_cents": ap.proposed_daily_rate_cents,
            "available_from": ap.available_from, "decision_note": ap.decision_note, "created_at": ap.created_at,
            "engineer": user_mini(eng) | {
                "title": prof.title if prof else "", "years_experience": prof.years_experience if prof else 0,
                "discipline": discipline_out(prof.discipline) if prof else None,
                "specializations": prof.specializations if prof else "",
                "verified": bool(prof and prof.verification_status == Verification.VERIFIED),
                "has_cv": bool(prof and prof.cv_file_id), "cv_file_id": prof.cv_file_id if prof else None,
                "average_rating": avg, "rating_count": count}}


def contract_out(db: Session, c: ServiceContract) -> dict:
    periods = []
    for p in c.periods:
        entries = db.scalars(select(TimeEntry).where(TimeEntry.period_id == p.id).order_by(TimeEntry.work_date)).all()
        recorded = sum(e.day_fraction for e in entries)
        periods.append({"id": p.id, "seq": p.seq, "start_date": p.start_date, "end_date": p.end_date,
                        "working_days": p.working_days, "status": p.status, "recorded_days": recorded,
                        "approved_days": p.approved_days, "amount_cents": p.amount_cents,
                        "estimated_cents": round(c.daily_rate_cents * recorded),
                        "review_comment": p.review_comment, "submitted_at": p.submitted_at,
                        "review_due_date": p.review_due_date, "review_escalated": p.review_escalated_at is not None,
                        "approved_at": p.approved_at,
                        "entries": [{"id": e.id, "work_date": e.work_date, "day_fraction": e.day_fraction,
                                     "hours": e.hours, "description": e.description, "status": e.status}
                                    for e in entries]})
    return {"id": c.id, "engineer": user_mini(c.engineer), "start_date": c.start_date, "end_date": c.end_date,
            "working_days": c.working_days, "daily_rate_cents": c.daily_rate_cents, "hours_per_day": c.hours_per_day,
            "period_length_days": c.period_length_days, "terms": c.terms,
            "org_signed_at": c.org_signed_at, "org_signature_name": c.org_signature_name,
            "engineer_signed_at": c.engineer_signed_at, "engineer_signature_name": c.engineer_signature_name,
            "ended_reason": c.ended_reason, "ended_at": c.ended_at,
            "contract_value_cents": c.daily_rate_cents * c.working_days,
            "approved_total_cents": sum(p["amount_cents"] for p in periods if p["status"] == "approved"),
            "periods": periods, "legal_notice_en": "Prototype contract. The working-day limit and the contract "
            "form are pending Saudi legal review (Blueprint D6).",
            "legal_notice_ar": "عقد تجريبي. الحد الأقصى لأيام العمل وصيغة العقد بانتظار المراجعة القانونية (القرار D6)."}
