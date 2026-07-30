"""Add inventory loans and a human-owned condition override.

Revision ID: 20260730_0009
Revises: 20260724_0008
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "20260730_0009"
down_revision = "20260724_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inventory_loans",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=False),
        # No authentication in local mode, so the typed-in name is what answers
        # "who has it"; the FK is only populated in multi-user deployments.
        sa.Column("borrower_name", sa.String(length=255), nullable=False),
        sa.Column("borrower_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="1"),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("borrowed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expected_return_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("returned_note", sa.Text(), nullable=True),
    )
    op.create_index("ix_inventory_loans_item_id", "inventory_loans", ["item_id"])
    op.create_index("ix_inventory_loans_borrower_user_id", "inventory_loans", ["borrower_user_id"])
    # Open loans are the hot query ("what is out right now"), and they are the
    # minority of rows once the lab has been using this for a while.
    op.create_index("ix_inventory_loans_returned_at", "inventory_loans", ["returned_at"])

    # The importer recomputes `condition` from the workbook on every re-import,
    # so a human "this one is broken" needs a column the importer never touches.
    op.add_column("inventory_items", sa.Column("condition_manual", sa.String(length=50), nullable=True))
    op.add_column("inventory_items", sa.Column("condition_note", sa.Text(), nullable=True))
    op.add_column("inventory_items", sa.Column("condition_marked_by", sa.String(length=255), nullable=True))
    op.add_column("inventory_items", sa.Column("condition_marked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_inventory_items_condition_manual", "inventory_items", ["condition_manual"])


def downgrade() -> None:
    op.drop_index("ix_inventory_items_condition_manual", table_name="inventory_items")
    op.drop_column("inventory_items", "condition_marked_at")
    op.drop_column("inventory_items", "condition_marked_by")
    op.drop_column("inventory_items", "condition_note")
    op.drop_column("inventory_items", "condition_manual")
    op.drop_index("ix_inventory_loans_returned_at", table_name="inventory_loans")
    op.drop_index("ix_inventory_loans_borrower_user_id", table_name="inventory_loans")
    op.drop_index("ix_inventory_loans_item_id", table_name="inventory_loans")
    op.drop_table("inventory_loans")
