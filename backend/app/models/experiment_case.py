"""Experiment case model."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class ExperimentCase(Base):
    """A laser experiment case managed by LaserClaw."""

    __tablename__ = "experiment_cases"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    cavity_type = Column(String(50), nullable=False)
    goal = Column(Text, nullable=False)
    status = Column(String(50), default="draft", index=True)
    visibility = Column(String(50), default="project", index=True)
    schema_version = Column(String(50), default="case_v2")
    tags = Column(JSON, default=list)
    parameters = Column(JSON, default=dict)
    symptoms = Column(JSON, default=list)
    measurements = Column(JSON, default=dict)
    safety_notes = Column(Text)
    conclusions = Column(Text)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project", back_populates="cases")
    owner = relationship("User")
    attachments = relationship("Attachment", back_populates="case", cascade="all, delete-orphan")
    generated_contents = relationship("GeneratedContent", back_populates="case", cascade="all, delete-orphan")
    knowledge_sources = relationship("KnowledgeSource", back_populates="case", cascade="all, delete-orphan")
    agent_tasks = relationship("AgentTask", back_populates="case", cascade="all, delete-orphan")
    case_modules = relationship("CaseModule", back_populates="case", cascade="all, delete-orphan")
    component_items = relationship("CaseComponentItem", back_populates="case", cascade="all, delete-orphan")
