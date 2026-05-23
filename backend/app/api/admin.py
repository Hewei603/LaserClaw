"""Administrative observability API."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth.security import Principal, get_current_principal
from ..database import get_db
from ..models import AuditLog
from ..schemas import AuditLogResponse

router = APIRouter()


@router.get("/audit-logs", response_model=list[AuditLogResponse])
async def list_audit_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """List recent audit logs. Requires admin/reviewer when auth is enabled."""
    if principal.role not in {"admin", "reviewer"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or reviewer role required")
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
