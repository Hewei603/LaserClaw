"""Prompt, workflow, and evaluation version records."""
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class PromptVersion(Base):
    """Versioned prompt template used by generation or agent workflows."""

    __tablename__ = "prompt_versions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    version = Column(String(50), nullable=False, index=True)
    content = Column(Text, nullable=False)
    metadata_json = Column(JSON, default=dict)
    is_active = Column(Boolean, default=False, index=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    created_by = relationship("User")

    __table_args__ = (UniqueConstraint("name", "version", name="uq_prompt_versions_name_version"),)


class WorkflowVersion(Base):
    """Versioned workflow definition for repeatable agent execution."""

    __tablename__ = "workflow_versions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    version = Column(String(50), nullable=False, index=True)
    definition = Column(JSON, nullable=False)
    metadata_json = Column(JSON, default=dict)
    is_active = Column(Boolean, default=False, index=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    created_by = relationship("User")

    __table_args__ = (UniqueConstraint("name", "version", name="uq_workflow_versions_name_version"),)


class RagEvalRun(Base):
    """Stored RAG evaluation or benchmark run."""

    __tablename__ = "rag_eval_runs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    dataset = Column(JSON, nullable=False)
    results = Column(JSON, nullable=False)
    total_questions = Column(Integer, default=0)
    hit_rate = Column(Float, default=0.0)
    mean_max_score = Column(Float, default=0.0)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    created_by = relationship("User")
