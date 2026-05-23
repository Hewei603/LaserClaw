"""Experiment case model."""
from sqlalchemy import Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class ExperimentCase(Base):
    """A laser experiment case managed by LaserClaw."""

    __tablename__ = "experiment_cases"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    cavity_type = Column(String(50), nullable=False)
    goal = Column(Text, nullable=False)
    parameters = Column(JSON, default=dict)
    symptoms = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    attachments = relationship("Attachment", back_populates="case", cascade="all, delete-orphan")
    generated_contents = relationship("GeneratedContent", back_populates="case", cascade="all, delete-orphan")
    knowledge_sources = relationship("KnowledgeSource", back_populates="case", cascade="all, delete-orphan")
    agent_tasks = relationship("AgentTask", back_populates="case", cascade="all, delete-orphan")
