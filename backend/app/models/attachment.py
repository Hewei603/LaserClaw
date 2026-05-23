"""Attachment model."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class Attachment(Base):
    """Uploaded file metadata."""

    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("experiment_cases.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    filepath = Column(String(512), nullable=False)
    file_type = Column(String(100))
    content_hash = Column(String(64), index=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("ExperimentCase", back_populates="attachments")
    knowledge_sources = relationship("KnowledgeSource", back_populates="attachment", cascade="all, delete-orphan")
