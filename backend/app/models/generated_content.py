"""Generated content model."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class GeneratedContent(Base):
    """AI-generated artifact for an experiment case."""

    __tablename__ = "generated_contents"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("experiment_cases.id"), nullable=False, index=True)
    content_type = Column(String(50), nullable=False, index=True)
    content = Column(JSON, nullable=False)
    model = Column(String(100))
    prompt_version = Column(String(100))
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    latency_ms = Column(Integer)
    cost_estimate = Column(String(50))
    generated_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("ExperimentCase", back_populates="generated_contents")
    knowledge_sources = relationship("KnowledgeSource", back_populates="generated_content", cascade="all, delete-orphan")
