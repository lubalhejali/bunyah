"""The starting point of the BUNYAH website. Run locally with:  uvicorn app.main:app --reload"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.errors import register_error_handlers
from app.routers import accounts, admin, auth, legacy, messages, projects, services, shared

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC = Path(__file__).parent / "static"
API = "/api/v1"
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    init_db()
    db = SessionLocal()
    try:
        from app import seed
        seed.ensure_reference_data(db)
        if s.demo_mode:
            seed.seed_demo(db)
        from app.services import checks
        checks.run(db)
    finally:
        db.close()
    log.info("BUNYAH started (env=%s, demo_mode=%s, storage=%s). Payments are SIMULATED.", s.env, s.demo_mode,
             s.storage_backend)
    if s.demo_mode and s.is_production:
        log.warning("DEMO_MODE is on in a production environment: one-click demo logins are available. "
                    "Use this only for a testing deployment with fictional data.")
    yield


app = FastAPI(
    title="BUNYAH API (prototype)",
    version="0.1.0",
    description="BUNYAH | بُنية – Saudi-focused B2B engineering services platform. Prototype: all payments are "
                "simulated, legal and financial assumptions are pending review.",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)
register_error_handlers(app)

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def _error(status: int, code: str, message: str, message_ar: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "message_ar": message_ar, "details": []}},
                        status_code=status)


@app.middleware("http")
async def security(request: Request, call_next):
    if request.method in UNSAFE and request.url.path.startswith("/api/"):
        # CSRF protection: our own pages always send this header; other websites can't add it.
        if request.headers.get("x-requested-with") != "fetch":
            return _error(403, "CSRF", "Request blocked for security reasons.", "تم حظر الطلب لأسباب أمنية.")
        max_bytes = (get_settings().max_upload_mb * 5 + 1) * 1024 * 1024  # up to 5 files per request
        length = request.headers.get("content-length")
        if length is None and request.headers.get("content-type", "").startswith("multipart/"):
            return _error(411, "LENGTH_REQUIRED", "Upload size unknown. Please try again.", "حجم الملف غير معروف.")
        if length is not None and (not length.isdigit() or int(length) > max_bytes):
            return _error(413, "FILE_TOO_LARGE", "The upload is too large.", "حجم الملف المرفوع كبير جدًا.")
    response = await call_next(request)
    h = response.headers
    if "content-security-policy" not in h and not request.url.path.startswith("/api/docs"):
        h["Content-Security-Policy"] = CSP
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "same-origin")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if get_settings().is_production:
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path.startswith("/api/") and "cache-control" not in h:
        h["Cache-Control"] = "no-store"
    return response


for r in (auth.router, accounts.router, projects.router, services.router, shared.router, messages.router,
          admin.router, legacy.router):
    app.include_router(r, prefix=API)


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})
