"""Knowledge and retrieval models."""
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class KnowledgeSource(Base):
    """A searchable source such as a case, attachment, or generated artifact."""

    __tablename__ = "knowledge_sources"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("experiment_cases.id"), nullable=True, index=True)
    attachment_id = Column(Integer, ForeignKey("attachments.id"), nullable=True, index=True)
    generated_content_id = Column(Integer, ForeignKey("generated_contents.id"), nullable=True, index=True)
    source_type = Column(String(50), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    uri = Column(String(512))
    content_hash = Column(String(64), index=True)
    governance_status = Column(String(50), default="draft", index=True)
    version = Column(Integer, default=1)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True))
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    case = relationship("ExperimentCase", back_populates="knowledge_sources")
    attachment = relationship("Attachment", back_populates="knowledge_sources")
    generated_content = relationship("GeneratedContent", back_populates="knowledge_sources")
    owner = relationship("User", foreign_keys=[owner_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])
    chunks = relationship("KnowledgeChunk", back_populates="source", cascade="all, delete-orphan")


class KnowledgeChunk(Base):
    """A searchable text chunk with a lightweight embedding payload."""

    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("knowledge_sources.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    token_count = Column(Integer, default=0)
    metadata_json = Column(JSON, default=dict)
    embedding = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    source = relationship("KnowledgeSource", back_populates="chunks")
    retrieval_results = relationship("RetrievalResult", back_populates="chunk", cascade="all, delete-orphan")


class RetrievalRun(Base):
    """Audit record for a knowledge search."""

    __tablename__ = "retrieval_runs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("agent_tasks.id"), nullable=True, index=True)
    query = Column(Text, nullable=False)
    filters_json = Column(JSON, default=dict)
    top_k = Column(Integer, default=5)
    max_score = Column(Float, default=0.0)
    confidence = Column(String(50), default="low")
    no_answer = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    results = relationship("RetrievalResult", back_populates="retrieval_run", cascade="all, delete-orphan")


class RetrievalResult(Base):
    """A retrieved chunk and score for a retrieval run."""

    __tablename__ = "retrieval_results"

    id = Column(Integer, primary_key=True, index=True)
    retrieval_run_id = Column(Integer, ForeignKey("retrieval_runs.id"), nullable=False, index=True)
    chunk_id = Column(Integer, ForeignKey("knowledge_chunks.id"), nullable=False, index=True)
    score = Column(Float, nullable=False)
    rank = Column(Integer, nullable=False)

    retrieval_run = relationship("RetrievalRun", back_populates="results")
    chunk = relationship("KnowledgeChunk", back_populates="retrieval_results")
