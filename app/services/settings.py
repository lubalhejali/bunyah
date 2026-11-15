"""Business rules an administrator can change on the "Platform settings" page.

Values marked pending_review are prototype assumptions that a Saudi lawyer or accountant must confirm
(Blueprint decisions D1, D2, D6 and the tax items). They are configurable on purpose and are never
presented as legally approved.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.errors import bad_request
from app.models import PlatformSetting, utcnow


@dataclass(frozen=True)
class Spec:
    default: object
    kind: str            # int | bool | float
    min: float | None = None
    max: float | None = None
    pending_review: str = ""   # which legal / accounting decision it waits for
    label_en: str = ""
    label_ar: str = ""


SPECS: dict[str, Spec] = {
    "model_b_max_working_days": Spec(90, "int", 1, 260, "D6 – legal review of the short-term contract limit",
                                     "Model B: maximum contract length (working days)",
                                     "النموذج ب: الحد الأقصى لمدة العقد (أيام عمل)"),
    "billing_period_working_days": Spec(20, "int", 5, 60, "",
                                        "Model B: billing period length (working days)",
                                        "النموذج ب: طول فترة الفوترة (أيام عمل)"),
    "near_expiry_working_days": Spec(5, "int", 1, 30, "",
                                     "Model B: mark contract 'near expiry' this many working days before the end",
                                     "النموذج ب: تنبيه قرب انتهاء العقد قبل هذا العدد من أيام العمل"),
    "review_window_working_days": Spec(5, "int", 1, 30, "",
                                       "Review window for deliverables and billing periods (working days)",
                                       "مهلة مراجعة التسليمات وفترات الفوترة (أيام عمل)"),
    "review_first_reminder_day": Spec(3, "int", 1, 30, "",
                                      "First review reminder on working day",
                                      "التذكير الأول في يوم العمل رقم"),
    "dispute_target_working_days": Spec(10, "int", 1, 60, "",
                                        "Target time for an administrative dispute decision (working days)",
                                        "المدة المستهدفة لقرار النزاع (أيام عمل)"),
    "appeal_window_working_days": Spec(5, "int", 1, 30, "",
                                       "Time to appeal a dispute decision (working days)",
                                       "مهلة الاستئناف على قرار النزاع (أيام عمل)"),
    "max_milestones": Spec(6, "int", 1, 6, "", "Maximum milestones per project", "الحد الأقصى للمراحل لكل مشروع"),
    "require_org_verification": Spec(True, "bool", pending_review="",
                                     label_en="Organizations must be verified before publishing",
                                     label_ar="يجب توثيق الجهة قبل النشر"),
    "require_engineer_verification": Spec(True, "bool",
                                          label_en="Engineers must be verified before applying",
                                          label_ar="يجب توثيق المهندس قبل التقديم"),
    "require_request_review": Spec(True, "bool", pending_review="D2/D6 – employment-like arrangements",
                                   label_en="Model B requests are reviewed by an administrator before publishing",
                                   label_ar="مراجعة طلبات النموذج ب من الإدارة قبل النشر"),
    "vat_percent": Spec(0.0, "float", 0, 100, "Tax treatment – accountant review",
                        "VAT shown on simulated invoices (%)", "ضريبة القيمة المضافة على الفواتير التجريبية (%)"),
}


def get(db: Session, key: str):
    spec = SPECS[key]
    row = db.get(PlatformSetting, key)
    return row.value.get("v", spec.default) if row else spec.default


def all_settings(db: Session) -> list[dict]:
    return [{"key": k, "value": get(db, k), "default": s.default, "kind": s.kind, "min": s.min, "max": s.max,
             "pending_review": s.pending_review, "label_en": s.label_en, "label_ar": s.label_ar}
            for k, s in SPECS.items()]


def set_value(db: Session, key: str, value, user_id: int) -> tuple[object, object]:
    if key not in SPECS:
        raise bad_request(f"Unknown setting '{key}'.", "إعداد غير معروف.")
    spec = SPECS[key]
    try:
        if spec.kind == "bool":
            if not isinstance(value, bool):
                raise ValueError
            v = value
        elif spec.kind == "int":
            if isinstance(value, bool) or int(value) != float(value):
                raise ValueError
            v = int(value)
        else:
            v = float(value)
    except (TypeError, ValueError):
        raise bad_request(f"'{key}' needs a {spec.kind} value.", "القيمة المدخلة غير صالحة لهذا الإعداد.")
    if spec.kind != "bool" and ((spec.min is not None and v < spec.min) or (spec.max is not None and v > spec.max)):
        raise bad_request(f"'{key}' must be between {spec.min} and {spec.max}.",
                          f"يجب أن تكون القيمة بين {spec.min} و {spec.max}.")
    old = get(db, key)
    row = db.get(PlatformSetting, key)
    if row is None:
        row = PlatformSetting(key=key, value={"v": v})
        db.add(row)
    row.value = {"v": v}
    row.updated_by, row.updated_at = user_id, utcnow()
    return old, v
