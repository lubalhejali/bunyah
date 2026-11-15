"""The database upgrade keeps old EngConnect data and converts it; the downgrade restores the old shape."""
import sqlite3
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parent.parent


def _cfg(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.attributes["url"] = url
    return cfg


def test_upgrade_converts_engconnect_data_and_downgrade_restores():
    path = Path(tempfile.mkdtemp()) / "legacy.db"
    url = f"sqlite:///{path.as_posix()}"
    cfg = _cfg(url)
    command.upgrade(cfg, "0001")                                    # the original EngConnect structure
    con = sqlite3.connect(path)
    con.executescript("""
        INSERT INTO users (id, email, password_hash, role, name, headline, bio, location, website, skills, company_name, created_at)
          VALUES (1, 'office@x.com', 'h', 'office', 'Olivia', '', 'Studio bio', 'Riyadh', '', '', 'Old Studio', '2025-01-01'),
                 (2, 'fl@x.com', 'h', 'freelancer', 'Frank', 'Steel designer', 'Bio', 'Jeddah', '', 'ETABS', '', '2025-01-01');
        INSERT INTO projects (id, office_id, title, description, requirements, category, work_mode, location, max_budget_cents,
          deadline, status, freelancer_id, accepted_offer_id, created_at)
          VALUES (1, 1, 'Old open project', 'desc', '', '', 'online', '', 100000, '2030-01-01', 'open', NULL, NULL, '2025-01-01'),
                 (2, 1, 'Old done project', 'desc', '', '', 'onsite', 'Riyadh', 100000, '2030-01-01', 'completed', 2, 1, '2025-01-01');
        INSERT INTO offers (id, project_id, freelancer_id, price_cents, delivery_date, message, status, created_at)
          VALUES (1, 2, 2, 90000, '2029-01-01', 'msg', 'accepted', '2025-01-01'),
                 (2, 1, 2, 90000, '2029-01-01', 'msg', 'pending', '2025-01-01');
        INSERT INTO reviews (id, project_id, office_id, freelancer_id, rating, text, created_at)
          VALUES (1, 2, 1, 2, 5, 'Great', '2025-02-01');
        INSERT INTO payments (id, project_id, office_id, freelancer_id, amount_cents, fee_cents, status, provider, provider_ref, created_at)
          VALUES (1, 2, 1, 2, 90000, 0, 'released', 'demo', '', '2025-01-15');
    """)
    con.commit()
    con.close()

    command.upgrade(cfg, "head")
    con = sqlite3.connect(path)
    q = lambda s: con.execute(s).fetchall()  # noqa: E731
    assert q("SELECT role FROM users ORDER BY id") == [("organization",), ("engineer",)]
    assert q("SELECT status, work_mode FROM projects ORDER BY id") == [("published", "remote"), ("completed", "onsite")]
    assert q("SELECT status FROM offers ORDER BY id") == [("accepted",), ("submitted",)]
    org = q("SELECT id, name FROM organizations")
    assert org and org[0][1] == "Old Studio"
    assert q("SELECT org_role FROM org_members WHERE user_id=1") == [("owner",)]
    assert q("SELECT org_id FROM projects") == [(org[0][0],), (org[0][0],)]
    assert q("SELECT title, software_skills FROM engineer_profiles") == [("Steel designer", "ETABS")]
    assert q("SELECT rating, reviewer_side FROM ratings") == [(5, "organization")]
    assert q("SELECT COUNT(*) FROM payments") == [(1,)]                    # legacy rows kept untouched
    assert q("SELECT COUNT(*) FROM reviews") == [(1,)]
    con.close()

    command.downgrade(cfg, "0001")
    con = sqlite3.connect(path)
    assert con.execute("SELECT role FROM users ORDER BY id").fetchall() == [("office",), ("freelancer",)]
    assert con.execute("SELECT status, work_mode FROM projects ORDER BY id").fetchall() == [("open", "online"), ("completed", "onsite")]
    assert con.execute("SELECT status FROM offers ORDER BY id").fetchall() == [("accepted",), ("pending",)]
    con.close()
    tables = set(inspect(create_engine(url)).get_table_names())
    assert "organizations" not in tables and "payments" in tables


def test_models_match_latest_migration():
    """The tables described in app/models.py and the migration files must not drift apart."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.database import Base

    path = Path(tempfile.mkdtemp()) / "fresh.db"
    url = f"sqlite:///{path.as_posix()}"
    command.upgrade(_cfg(url), "head")
    eng = create_engine(url)
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": False}), Base.metadata)
    # SQLite reports unnamed foreign keys differently; ignore those, everything else must match.
    real = [d for d in diff if not (isinstance(d, tuple) and d[0] in ("add_fk", "remove_fk"))]
    assert real == [], real
