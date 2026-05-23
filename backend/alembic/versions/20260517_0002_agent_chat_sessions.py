"""add agent chat sessions

Revision ID: 20260517_0002
Revises: 20260515_0001
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa

revision = "20260517_0002"
down_revision = "20260515_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_chat_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("experiment_cases.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_chat_sessions_id", "agent_chat_sessions", ["id"])
    op.create_index("ix_agent_chat_sessions_case_id", "agent_chat_sessions", ["case_id"])
    op.create_index("ix_agent_chat_sessions_user_id", "agent_chat_sessions", ["user_id"])

    op.create_table(
        "agent_chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("agent_chat_sessions.id"), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_chat_messages_id", "agent_chat_messages", ["id"])
    op.create_index("ix_agent_chat_messages_session_id", "agent_chat_messages", ["session_id"])


def downgrade() -> None:
    op.drop_table("agent_chat_messages")
    op.drop_table("agent_chat_sessions")
