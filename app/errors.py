"""One error format for the whole API:

{"error": {"code": "NOT_FOUND", "message": "Project not found.", "message_ar": "...", "details": [...]}}

`message` is English, `message_ar` Arabic. The page shows the one that matches the chosen language.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, message_ar: str = "", details: list | None = None):
        self.status, self.code, self.message = status, code, message
        self.message_ar = message_ar
        self.details = details or []


def not_found(what: str = "Item", what_ar: str = "العنصر") -> ApiError:
    return ApiError(404, "NOT_FOUND", f"{what} not found.", f"{what_ar} غير موجود.")


def forbidden(message: str = "You don't have permission to do this.",
              message_ar: str = "ليست لديك صلاحية للقيام بهذا الإجراء.") -> ApiError:
    return ApiError(403, "FORBIDDEN", message, message_ar)


def conflict(message: str, message_ar: str = "", code: str = "CONFLICT") -> ApiError:
    return ApiError(409, code, message, message_ar)


def bad_request(message: str, message_ar: str = "", code: str = "BAD_REQUEST") -> ApiError:
    return ApiError(400, code, message, message_ar)


def _body(code: str, message: str, message_ar: str = "", details: list | None = None) -> dict:
    return {"error": {"code": code, "message": message, "message_ar": message_ar, "details": details or []}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(_body(exc.code, exc.message, exc.message_ar, exc.details), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = []
        for e in exc.errors():
            loc = [str(p) for p in e.get("loc", []) if p not in ("body", "query", "path")]
            details.append({"field": ".".join(loc), "issue": e.get("msg", "Invalid value")})
        first = details[0] if details else {"field": "", "issue": "Invalid input"}
        msg = f"{first['field']}: {first['issue']}" if first["field"] else first["issue"]
        ar = f"يرجى مراجعة الحقل: {first['field']}" if first["field"] else "يرجى مراجعة البيانات المدخلة."
        return JSONResponse(_body("VALIDATION_ERROR", msg, ar, details), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(
            exc.status_code, "HTTP_ERROR")
        return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        log.exception("Unhandled error", exc_info=exc)
        return JSONResponse(_body("SERVER_ERROR", "Something went wrong on our side. Please try again.",
                                  "حدث خطأ من جهتنا. يرجى المحاولة مرة أخرى."), 500)
