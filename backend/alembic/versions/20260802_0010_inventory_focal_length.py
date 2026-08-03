"""Add inventory_items.focal_length_mm for lens rows.

Revision ID: 20260802_0010
Revises: 20260730_0009
Create Date: 2026-08-02
"""
from alembic import op
import sqlalchemy as sa

revision = "20260802_0010"
down_revision = "20260730_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The lab workbook writes lens focal lengths (F=300mm / f=250 mm / F100)
    # into the same column as mirror ROCs; without a field of its own the
    # importer silently dropped them and every lens looked geometry-less.
    op.add_column("inventory_items", sa.Column("focal_length_mm", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("inventory_items", "focal_length_mm")
