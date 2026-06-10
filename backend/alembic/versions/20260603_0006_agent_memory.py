"""Add agent session summaries and memory items.

Revision ID: 20260603_0006
Revises: 20260602_0005
Create Date: 2026-06-03
"""
from alembic import op
import sqlalchemy as sa


revision = "20260603_0006"
down_revision = "20260602_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_session_summaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("agent_chat_sessions.id"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=True),
        sa.Column("last_message_id", sa.Integer(), sa.ForeignKey("agent_chat_messages.id"), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_session_summaries_id", "agent_session_summaries", ["id"])
    op.create_index("ix_agent_session_summaries_session_id", "agent_session_summaries", ["session_id"])

    op.create_table(
        "agent_memory_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("agent_chat_sessions.id"), nullable=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("experiment_cases.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("memory_type", sa.String(length=50), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=True),
        sa.Column("source_message_id", sa.Integer(), sa.ForeignKey("agent_chat_messages.id"), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_memory_items_id", "agent_memory_items", ["id"])
    op.create_index("ix_agent_memory_items_session_id", "agent_memory_items", ["session_id"])
    op.create_index("ix_agent_memory_items_case_id", "agent_memory_items", ["case_id"])
    op.create_index("ix_agent_memory_items_user_id", "agent_memory_items", ["user_id"])
    op.create_index("ix_agent_memory_items_memory_type", "agent_memory_items", ["memory_type"])
    op.create_index("ix_agent_memory_items_importance", "agent_memory_items", ["importance"])


def downgrade() -> None:
    op.drop_table("agent_memory_items")
    op.drop_table("agent_session_summaries")
