"""Agent task and chat models."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class AgentChatSession(Base):
    """A persistent case-aware Agent chat session."""

    __tablename__ = "agent_chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("experiment_cases.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    title = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    case = relationship("ExperimentCase")
    user = relationship("User")
    messages = relationship(
        "AgentChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AgentChatMessage.created_at",
    )


class AgentChatMessage(Base):
    """A persisted message in an Agent chat session."""

    __tablename__ = "agent_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("agent_chat_sessions.id"), nullable=False, index=True)
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("AgentChatSession", back_populates="messages")


class AgentTask(Base):
    """A stateful Agent run requested by a user."""

    __tablename__ = "agent_tasks"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("experiment_cases.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    goal = Column(Text, nullable=False)
    mode = Column(String(50), default="troubleshooting")
    status = Column(String(50), default="pending", index=True)
    risk_level = Column(String(50), default="medium")
    final_content_id = Column(Integer, ForeignKey("generated_contents.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    case = relationship("ExperimentCase", back_populates="agent_tasks")
    user = relationship("User", back_populates="agent_tasks")
    steps = relationship("AgentStep", back_populates="task", cascade="all, delete-orphan", order_by="AgentStep.step_index")
    tool_calls = relationship("AgentToolCall", back_populates="task", cascade="all, delete-orphan")
    final_content = relationship("GeneratedContent")


class AgentStep(Base):
    """A persisted Agent planning or execution step."""

    __tablename__ = "agent_steps"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("agent_tasks.id"), nullable=False, index=True)
    step_index = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    status = Column(String(50), default="pending")
    rationale = Column(Text)
    result_summary = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    task = relationship("AgentTask", back_populates="steps")
    tool_calls = relationship("AgentToolCall", back_populates="step", cascade="all, delete-orphan")


class AgentToolCall(Base):
    """A persisted tool call made by the Agent."""

    __tablename__ = "agent_tool_calls"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("agent_tasks.id"), nullable=False, index=True)
    step_id = Column(Integer, ForeignKey("agent_steps.id"), nullable=True, index=True)
    tool_name = Column(String(100), nullable=False, index=True)
    input_json = Column(JSON, default=dict)
    output_json = Column(JSON, default=dict)
    status = Column(String(50), default="completed")
    latency_ms = Column(Integer)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship("AgentTask", back_populates="tool_calls")
    step = relationship("AgentStep", back_populates="tool_calls")


class AgentSessionSummary(Base):
    """Rolling summary for a long-running chat session.

    Compressed once the session exceeds SUMMARY_TRIGGER_MESSAGES. Older
    messages are distilled into this record so the prompt window stays
    bounded while key conclusions are preserved.
    """

    __tablename__ = "agent_session_summaries"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("agent_chat_sessions.id"), nullable=False, index=True)
    summary = Column(Text, nullable=False)
    message_count = Column(Integer, default=0)
    last_message_id = Column(Integer, ForeignKey("agent_chat_messages.id"), nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    session = relationship("AgentChatSession")


class AgentMemoryItem(Base):
    """A durable fact, decision, or preference extracted from a chat session.

    Extracted by the provider's summarize_chat call and persisted so that
    future turns can surface relevant context even after the raw messages
    have been compressed.
    """

    __tablename__ = "agent_memory_items"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("agent_chat_sessions.id"), nullable=True, index=True)
    case_id = Column(Integer, ForeignKey("experiment_cases.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    memory_type = Column(String(50), default="fact", index=True)
    content = Column(Text, nullable=False)
    importance = Column(Integer, default=1, index=True)
    source_message_id = Column(Integer, ForeignKey("agent_chat_messages.id"), nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("AgentChatSession")
