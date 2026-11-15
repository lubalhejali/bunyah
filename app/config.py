"""Server settings come from environment variables (on Render: the service's "Environment" tab).

Locally you can put them in a file named `.env` next to this project (see `.env.example`).
Business rules that an administrator may change (fees, review windows, the Model B day limit...) are NOT here:
they live in the database and are edited on the admin "Platform settings" page (see services/settings.py).
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-secret-change-me-dev-only-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "development" on your computer, "production" on any Render deployment (turns on secure cookies).
    env: str = "development"
    # Signs login cookies. MUST be a long random value on Render.
    secret_key: str = DEV_SECRET
    database_url: str = "sqlite:///./local.db"
    public_base_url: str = "http://localhost:8000"

    # DEMO_MODE=true: fills an empty database with fictional demo accounts and data, shows one-click demo
    # logins on the login page and DEMO banners. Use it on your computer and on a testing deployment only.
    demo_mode: bool = True

    currency: str = "SAR"

    # Real payments are not part of this prototype. The old EngConnect Stripe code is kept in app/legacy/
    # but cannot run unless this is true AND a Stripe key is set. Leave it false.
    legacy_payments_enabled: bool = False
    stripe_secret_key: str = ""

    # Bootstrap administrators: accounts with these e-mails are administrators (register them first).
    admin_emails: str = ""

    # Where uploaded file contents are kept: "database" (default; survives restarts on Render) or
    # "local" (a folder on this computer, set by LOCAL_STORAGE_DIR). Object storage can be added later.
    storage_backend: str = "database"
    local_storage_dir: str = "./uploads"

    max_upload_mb: int = 25
    session_hours: int = 12

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production and (s.secret_key == DEV_SECRET or len(s.secret_key) < 32):
        raise RuntimeError("SECRET_KEY must be set to a long random value in production.")
    if s.storage_backend not in ("database", "local"):
        raise RuntimeError("STORAGE_BACKEND must be 'database' or 'local'.")
    return s
