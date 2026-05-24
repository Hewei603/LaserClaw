"""add retrieval confidence fields

Revision ID: 20260523_0003
Revises: 20260517_0002
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa

revision = "20260523_0003"
down_revision = "20260517_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("retrieval_runs", sa.Column("max_score", sa.Float(), nullable=True))
    op.add_column("retrieval_runs", sa.Column("confidence", sa.String(50), nullable=True))
    op.add_column("retrieval_runs", sa.Column("no_answer", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("retrieval_runs", "no_answer")
    op.drop_column("retrieval_runs", "confidence")
    op.drop_column("retrieval_runs", "max_score")
