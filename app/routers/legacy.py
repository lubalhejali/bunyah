"""Old EngConnect payment endpoints (Stripe checkout, escrow, wallet withdrawals).

They are switched off because BUNYAH must not process real payments or hold funds until the payment-custody
decision (Blueprint D1) is approved. The original code is kept in _backup/ and described in docs/LEGACY.md.
Each address answers 410 Gone with an explanation instead of silently disappearing."""
from fastapi import APIRouter

from app.errors import ApiError

router = APIRouter(tags=["legacy (switched off)"], include_in_schema=True)

MSG = ("This EngConnect payment feature is switched off in the BUNYAH prototype. Payments are simulated; "
       "see /finance.")
MSG_AR = "ميزة الدفع هذه من EngConnect متوقفة في نموذج بُنية. المدفوعات تجريبية؛ راجع صفحة المالية."


def _gone():
    raise ApiError(410, "FEATURE_SWITCHED_OFF", MSG, MSG_AR)


for path, method in [("/projects/{project_id}/payment", "post"), ("/projects/{project_id}/payment/confirm", "post"),
                     ("/payments", "get"), ("/wallet", "get"), ("/wallet/withdrawals", "post"),
                     ("/admin/withdrawals", "get"), ("/admin/escrow", "get")]:
    router.add_api_route(path, _gone, methods=[method.upper()], status_code=410,
                         summary="Switched off (EngConnect legacy)")
