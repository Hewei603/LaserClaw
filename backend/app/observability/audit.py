"""Audit helpers."""
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..models import AuditLog


def record_audit(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    actor: str = "system",
    user_id: Optional[int] = None,
    request_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> AuditLog:
    """Persist an audit event."""
    event = AuditLog(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor=actor,
        user_id=user_id,
        request_id=request_id,
        metadata_json=metadata or {},
    )
    db.add(event)
    return event
