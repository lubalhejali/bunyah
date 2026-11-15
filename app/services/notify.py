"""In-app notifications in Arabic and English. E-mail is not configured in the prototype, so every
notification is recorded with email_status='not_configured' (ready for an e-mail provider later)."""
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification, OrgMember, OrgRole, User

# kind -> (English, Arabic). {t} is the item title.
TEMPLATES: dict[str, tuple[str, str]] = {
    "proposal_received": ("New proposal on '{t}'", "عرض جديد على «{t}»"),
    "proposal_shortlisted": ("Your proposal for '{t}' was shortlisted", "تمت إضافة عرضك على «{t}» إلى القائمة المختصرة"),
    "proposal_clarification": ("Clarification requested on your proposal for '{t}'", "طُلب توضيح على عرضك لمشروع «{t}»"),
    "proposal_clarified": ("The engineer answered your question on '{t}'", "أجاب المهندس على استفسارك في «{t}»"),
    "proposal_accepted": ("Your proposal for '{t}' was accepted", "تم قبول عرضك على «{t}»"),
    "proposal_rejected": ("Your proposal for '{t}' was not selected", "لم يتم اختيار عرضك على «{t}»"),
    "agreement_accepted": ("The engineer accepted the agreement for '{t}'", "وافق المهندس على اتفاقية «{t}»"),
    "project_started": ("Work has started on '{t}'", "بدأ العمل على «{t}»"),
    "deliverable_uploaded": ("New deliverable version on '{t}'", "نسخة تسليم جديدة في «{t}»"),
    "submitted_for_review": ("'{t}' was submitted for your review", "تم تقديم «{t}» للمراجعة"),
    "version_approved": ("A deliverable on '{t}' was approved", "تم اعتماد تسليم في «{t}»"),
    "revision_requested": ("Revision requested on '{t}'", "طُلب تعديل على «{t}»"),
    "project_approved": ("Final delivery approved for '{t}'", "تم اعتماد التسليم النهائي لـ «{t}»"),
    "project_completed": ("'{t}' is completed", "اكتمل «{t}»"),
    "review_reminder": ("Reminder: a review is waiting on '{t}'", "تذكير: توجد مراجعة بانتظارك في «{t}»"),
    "review_overdue": ("Review window passed on '{t}' – escalated to the BUNYAH team",
                       "انتهت مهلة المراجعة في «{t}» وتم تصعيدها لفريق بُنية"),
    "milestone_approved": ("Milestone approved on '{t}'", "تم اعتماد مرحلة في «{t}»"),
    "invoice_issued": ("Simulated invoice issued for '{t}'", "صدرت فاتورة تجريبية لـ «{t}»"),
    "payment_recorded": ("Simulated payment recorded for '{t}'", "تم تسجيل دفعة تجريبية لـ «{t}»"),
    "payout_sent": ("Simulated payout recorded for '{t}'", "تم تسجيل تحويل تجريبي لـ «{t}»"),
    "request_submitted": ("Service request '{t}' is waiting for review", "طلب الخدمة «{t}» بانتظار المراجعة"),
    "request_published": ("Your service request '{t}' was published", "تم نشر طلب الخدمة «{t}»"),
    "request_returned": ("Your service request '{t}' needs changes", "طلب الخدمة «{t}» يحتاج إلى تعديلات"),
    "application_received": ("New application on '{t}'", "طلب تقديم جديد على «{t}»"),
    "application_shortlisted": ("You were shortlisted for '{t}'", "تمت إضافتك إلى القائمة المختصرة لـ «{t}»"),
    "application_selected": ("You were selected for '{t}'", "تم اختيارك لـ «{t}»"),
    "application_rejected": ("Your application for '{t}' was not selected", "لم يتم اختيار طلبك لـ «{t}»"),
    "contract_ready": ("Contract for '{t}' is ready to sign", "عقد «{t}» جاهز للتوقيع"),
    "contract_signed": ("Contract for '{t}' was signed by the other party", "وقّع الطرف الآخر عقد «{t}»"),
    "contract_active": ("Contract for '{t}' is now active", "أصبح عقد «{t}» ساريًا"),
    "contract_near_expiry": ("Contract for '{t}' ends soon", "يقترب انتهاء عقد «{t}»"),
    "contract_ended": ("Contract for '{t}' has ended", "انتهى عقد «{t}»"),
    "period_submitted": ("Billing period submitted on '{t}'", "تم تقديم فترة فوترة في «{t}»"),
    "period_approved": ("Billing period approved on '{t}'", "تم اعتماد فترة فوترة في «{t}»"),
    "period_revision": ("Changes requested on a billing period of '{t}'", "طُلبت تعديلات على فترة فوترة في «{t}»"),
    "dispute_opened": ("A dispute was opened on '{t}'", "تم فتح نزاع على «{t}»"),
    "dispute_response": ("New response in the dispute on '{t}'", "رد جديد في النزاع على «{t}»"),
    "dispute_decided": ("A decision was recorded in the dispute on '{t}'", "صدر قرار في النزاع على «{t}»"),
    "dispute_appealed": ("The dispute decision on '{t}' was appealed", "تم استئناف قرار النزاع على «{t}»"),
    "dispute_closed": ("The dispute on '{t}' is closed", "أُغلق النزاع على «{t}»"),
    "verification_submitted": ("New verification request: {t}", "طلب توثيق جديد: {t}"),
    "verification_approved": ("Your account '{t}' is verified", "تم توثيق حسابك «{t}»"),
    "verification_rejected": ("Verification of '{t}' was not approved", "لم تتم الموافقة على توثيق «{t}»"),
    "verification_needs_info": ("More information is needed to verify '{t}'", "مطلوب معلومات إضافية لتوثيق «{t}»"),
    "new_message": ("New message from {t}", "رسالة جديدة من {t}"),
    "rating_received": ("You received a rating on '{t}'", "تلقيت تقييمًا على «{t}»"),
    "announcement": ("{t}", "{t}"),
}


def notify(db: Session, user_ids: Iterable[int], kind: str, title: str, link: str = "",
           title_ar: str | None = None) -> None:
    en, ar = TEMPLATES[kind]
    t_en = en.format(t=title)[:300]
    t_ar = ar.format(t=title_ar or title)[:300]
    for uid in dict.fromkeys(u for u in user_ids if u):
        db.add(Notification(user_id=uid, kind=kind, title_en=t_en, title_ar=t_ar, link=link[:200]))


def org_user_ids(db: Session, org_id: int | None, roles: tuple[str, ...] | None = None) -> list[int]:
    """Active members of an organization, optionally only some roles (e.g. reviewers)."""
    if org_id is None:
        return []
    stmt = select(OrgMember.user_id).where(OrgMember.org_id == org_id, OrgMember.is_active.is_(True))
    if roles:
        stmt = stmt.where(OrgMember.org_role.in_(roles))
    return list(db.scalars(stmt).all())


def admin_user_ids(db: Session) -> list[int]:
    from app.security import admin_ids
    return admin_ids(db)


MANAGERS = (OrgRole.OWNER, OrgRole.PROJECT_MANAGER)
REVIEWERS = (OrgRole.OWNER, OrgRole.PROJECT_MANAGER, OrgRole.TECHNICAL_REVIEWER)
FINANCE = (OrgRole.OWNER, OrgRole.FINANCE)
_ = User  # (imported for type hints in callers)
