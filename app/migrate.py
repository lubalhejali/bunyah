"""Brings the database structure up to date. Runs automatically when the app starts.

Run by hand:  python -m app.migrate          (upgrade to the latest version)
              python -m app.migrate current  (show the version the database is on)

Older EngConnect databases were created without migration tracking; they are recognised and marked as
version 0001 (the EngConnect structure) before the BUNYAH migrations run, so existing data is converted, not lost.
"""
import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.config import get_settings
from app.database import engine

log = logging.getLogger("app.migrate")
ROOT = Path(__file__).resolve().parent.parent


def _config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.attributes["url"] = get_settings().sqlalchemy_url
    return cfg


def upgrade() -> None:
    cfg = _config()
    with engine.connect() as conn:
        if conn.dialect.name == "sqlite":
            # SQLite rebuilds tables during some migration steps; link checks must be off meanwhile.
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            conn.commit()
        tables = set(inspect(conn).get_table_names())
        cfg.attributes["connection"] = conn
        if "alembic_version" not in tables and "users" in tables:
            log.warning("Existing EngConnect database found without version tracking: marking it as 0001.")
            command.stamp(cfg, "0001")
        command.upgrade(cfg, "head")
        conn.commit()
        if conn.dialect.name == "sqlite":
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")


def current() -> None:
    cfg = _config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.current(cfg, verbose=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    (current if sys.argv[1:] == ["current"] else upgrade)()
