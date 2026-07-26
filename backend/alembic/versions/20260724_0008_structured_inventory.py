"""Add structured optics inventory (inventory_items + coating_specs).

Revision ID: 20260724_0008
Revises: 20260610_0007
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa


revision = "20260724_0008"
down_revision = "20260610_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inventory_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("diameter_mm", sa.Float(), nullable=True),
        sa.Column("roc_mm", sa.Float(), nullable=True),
        sa.Column("roc_is_flat", sa.Boolean(), nullable=True),
        sa.Column("thickness_mm", sa.Float(), nullable=True),
        sa.Column("dimensions", sa.String(length=100), nullable=True),
        sa.Column("cut_angle_theta_deg", sa.Float(), nullable=True),
        sa.Column("cut_angle_phi_deg", sa.Float(), nullable=True),
        sa.Column("cut_axis", sa.String(length=50), nullable=True),
        sa.Column("doping_pct", sa.Float(), nullable=True),
        sa.Column("material", sa.String(length=100), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("location", sa.String(length=100), nullable=True),
        sa.Column("keeper", sa.String(length=255), nullable=True),
        sa.Column("vendor", sa.String(length=255), nullable=True),
        sa.Column("raw_spec", sa.Text(), nullable=True),
        sa.Column("parse_confidence", sa.String(length=20), nullable=True),
        sa.Column("parse_notes", sa.JSON(), nullable=True),
        sa.Column("condition", sa.String(length=50), nullable=True),
        sa.Column("source_file", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_inventory_items_id", "inventory_items", ["id"])
    op.create_index("ix_inventory_items_category", "inventory_items", ["category"])
    op.create_index("ix_inventory_items_name", "inventory_items", ["name"])
    op.create_index("ix_inventory_items_location", "inventory_items", ["location"])
    op.create_index("ix_inventory_items_parse_confidence", "inventory_items", ["parse_confidence"])
    op.create_index("ix_inventory_items_condition", "inventory_items", ["condition"])

    op.create_table(
        "coating_specs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=False),
        sa.Column("surface", sa.String(length=10), nullable=False),
        sa.Column("wl_min_nm", sa.Float(), nullable=False),
        sa.Column("wl_max_nm", sa.Float(), nullable=False),
        sa.Column("function", sa.String(length=10), nullable=False),
        sa.Column("value_type", sa.String(length=5), nullable=True),
        sa.Column("comparator", sa.String(length=5), nullable=True),
        sa.Column("value_pct", sa.Float(), nullable=True),
        sa.Column("raw_fragment", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_coating_specs_id", "coating_specs", ["id"])
    op.create_index("ix_coating_specs_item_id", "coating_specs", ["item_id"])
    op.create_index("ix_coating_specs_surface", "coating_specs", ["surface"])
    op.create_index("ix_coating_specs_wl_min_nm", "coating_specs", ["wl_min_nm"])
    op.create_index("ix_coating_specs_wl_max_nm", "coating_specs", ["wl_max_nm"])
    op.create_index("ix_coating_specs_function", "coating_specs", ["function"])


def downgrade() -> None:
    op.drop_table("coating_specs")
    op.drop_table("inventory_items")
