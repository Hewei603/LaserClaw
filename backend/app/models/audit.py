"""Audit log model."""
from sqlalchemy import Column, DateTime, Integer, JSON, String
from sqlalchemy.sql import func

from ..database import Base


class AuditLog(Base):
    """Append-only audit trail for user and Agent actions."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    actor = Column(String(255), default="anonymous")
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(100), nullable=True, index=True)
    request_id = Column(String(100), nullable=True, index=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
