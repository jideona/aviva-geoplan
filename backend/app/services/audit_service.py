"""Audit trail writing (SRD FR-AUD-001 to FR-AUD-003).

Audit rows are append-only. Nothing in the application updates or deletes them.
"""
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.db.models.audit import AuditLog
from app.db.models.user import User


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Field-level changes only. Unchanged fields are not recorded."""
    out: dict[str, Any] = {}
    for key in set(before) | set(after):
        b, a = before.get(key), after.get(key)
        if b != a:
            out[key] = {"before": _plain(b), "after": _plain(a)}
    return out


def _plain(value: Any) -> Any:
    if isinstance(value, (uuid.UUID,)):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def record(
    db: Session,
    *,
    actor: User | None,
    entity_type: str,
    entity_id: uuid.UUID | None,
    action: str,
    project_id: uuid.UUID | None = None,
    changes: dict[str, Any] | None = None,
) -> None:
    db.add(AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_email=actor.email if actor else None,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        project_id=project_id,
        changes=changes or None,
        request_id=request_id_var.get(),
    ))
