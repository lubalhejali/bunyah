"""The allowed status changes ("state machines") for both service models.

Model A and Model B are deliberately separate tables with separate rules. Any status change that is not listed
here is refused by the server, whatever the page shows.
"""
from app.errors import conflict
from app.models import ProjectStatus as P
from app.models import RequestStatus as R

PROJECT_FLOW: dict[str, set[str]] = {
    P.DRAFT: {P.PUBLISHED, P.CANCELLED},
    P.PUBLISHED: {P.APPLICATIONS_CLOSED, P.CANCELLED},
    P.APPLICATIONS_CLOSED: {P.UNDER_EVALUATION, P.PUBLISHED, P.CANCELLED},
    P.UNDER_EVALUATION: {P.SHORTLISTED, P.PROPOSAL_ACCEPTED, P.CANCELLED},
    P.SHORTLISTED: {P.PROPOSAL_ACCEPTED, P.UNDER_EVALUATION, P.CANCELLED},
    P.PROPOSAL_ACCEPTED: {P.IN_PROGRESS, P.UNDER_EVALUATION, P.CANCELLED},
    P.IN_PROGRESS: {P.SUBMITTED, P.DISPUTED},
    P.SUBMITTED: {P.REVISION, P.APPROVED, P.DISPUTED},
    P.REVISION: {P.RESUBMITTED, P.DISPUTED},
    P.RESUBMITTED: {P.REVISION, P.APPROVED, P.DISPUTED},
    P.APPROVED: {P.COMPLETED, P.DISPUTED},
    # Leaving "disputed" only happens through an administrator's recorded decision.
    P.DISPUTED: {P.IN_PROGRESS, P.SUBMITTED, P.REVISION, P.RESUBMITTED, P.APPROVED, P.COMPLETED, P.CANCELLED},
    P.COMPLETED: set(),
    P.CANCELLED: set(),
}

REQUEST_FLOW: dict[str, set[str]] = {
    R.DRAFT: {R.SUBMITTED, R.CANCELLED},
    R.SUBMITTED: {R.PENDING_REVIEW, R.DRAFT, R.CANCELLED},
    R.PENDING_REVIEW: {R.PUBLISHED, R.DRAFT},           # admin publishes or returns it for changes
    R.PUBLISHED: {R.APPLICATIONS_OPEN, R.CANCELLED},
    R.APPLICATIONS_OPEN: {R.UNDER_EVALUATION, R.CANCELLED},
    R.UNDER_EVALUATION: {R.SELECTED, R.APPLICATIONS_OPEN, R.CANCELLED},
    R.SELECTED: {R.CONTRACT_PREPARATION, R.UNDER_EVALUATION, R.CANCELLED},
    R.CONTRACT_PREPARATION: {R.AWAITING_SIGNATURES, R.UNDER_EVALUATION, R.CANCELLED},
    R.AWAITING_SIGNATURES: {R.ACTIVE, R.CONTRACT_PREPARATION, R.CANCELLED},
    R.ACTIVE: {R.NEAR_EXPIRY, R.COMPLETED, R.TERMINATED, R.DISPUTED},
    R.NEAR_EXPIRY: {R.COMPLETED, R.TERMINATED, R.DISPUTED},
    R.DISPUTED: {R.ACTIVE, R.NEAR_EXPIRY, R.COMPLETED, R.TERMINATED},
    R.COMPLETED: set(),
    R.TERMINATED: set(),
    R.CANCELLED: set(),
}

LABELS_AR = {
    "draft": "مسودة", "published": "منشور", "applications_closed": "أُغلق استقبال العروض",
    "under_evaluation": "قيد التقييم", "shortlisted": "قائمة مختصرة", "proposal_accepted": "تم قبول العرض",
    "in_progress": "قيد التنفيذ", "submitted": "مقدم للمراجعة", "revision_requested": "مطلوب تعديل",
    "resubmitted": "أعيد تقديمه", "approved": "معتمد", "completed": "مكتمل", "cancelled": "ملغى",
    "disputed": "متنازع عليه", "pending_review": "قيد مراجعة الإدارة", "applications_open": "التقديم مفتوح",
    "selected": "تم الاختيار", "contract_preparation": "إعداد العقد", "awaiting_signatures": "بانتظار التوقيع",
    "active": "ساري", "near_expiry": "قرب الانتهاء", "terminated": "منتهي (إنهاء مبكر)",
}


def _nice(s: str) -> str:
    return s.replace("_", " ")


def check(flow: dict[str, set[str]], current: str, new: str) -> None:
    if new not in flow.get(current, set()):
        raise conflict(
            f"This can't be done while the status is '{_nice(current)}' (it can't move to '{_nice(new)}').",
            f"لا يمكن تنفيذ هذا الإجراء والحالة «{LABELS_AR.get(current, current)}».",
            "INVALID_TRANSITION",
        )


def require_status(current: str, *allowed: str) -> None:
    if current not in allowed:
        raise conflict(f"This can't be done while the status is '{_nice(current)}'.",
                       f"لا يمكن تنفيذ هذا الإجراء والحالة «{LABELS_AR.get(current, current)}».",
                       "INVALID_STATUS")
