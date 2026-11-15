"""Audit log: a permanent record of sensitive actions (verification, fees, settings, disputes, money, roles).
Rows are only ever added, never edited or deleted by the application."""
from sqlalchemy.orm import Session

from app.models import AuditLog, User


def record(db: Session, actor: User | None, action: str, entity_type: str = "", entity_id: int | None = None,
           ip: str = "", **details) -> None:
    db.add(AuditLog(actor_id=actor.id if actor else None, action=action, entity_type=entity_type,
                    entity_id=entity_id, details=_clean(details), ip=ip[:64]))


def _clean(details: dict) -> dict:
    out = {}
    for k, v in details.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v if not isinstance(v, str) else v[:500]
        else:
            out[k] = str(v)[:500]
    return out
