"""Add case modules and per-case component lists.

Revision ID: 20260610_0007
Revises: 20260603_0006
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa


revision = "20260610_0007"
down_revision = "20260603_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_modules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("experiment_cases.id"), nullable=False),
        sa.Column("module_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_case_modules_id", "case_modules", ["id"])
    op.create_index("ix_case_modules_case_id", "case_modules", ["case_id"])
    op.create_index("ix_case_modules_module_type", "case_modules", ["module_type"])
    op.create_index("ix_case_modules_status", "case_modules", ["status"])

    op.create_table(
        "case_module_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("module_id", sa.Integer(), sa.ForeignKey("case_modules.id"), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("filepath", sa.String(length=1024), nullable=False),
        sa.Column("file_type", sa.String(length=100), nullable=True),
        sa.Column("file_role", sa.String(length=50), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_case_module_files_id", "case_module_files", ["id"])
    op.create_index("ix_case_module_files_module_id", "case_module_files", ["module_id"])
    op.create_index("ix_case_module_files_file_role", "case_module_files", ["file_role"])
    op.create_index("ix_case_module_files_content_hash", "case_module_files", ["content_hash"])

    op.create_table(
        "case_component_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("experiment_cases.id"), nullable=False),
        sa.Column("module_id", sa.Integer(), sa.ForeignKey("case_modules.id"), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("specification", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=True),
        sa.Column("owned", sa.Boolean(), nullable=True),
        sa.Column("procurement_status", sa.String(length=50), nullable=True),
        sa.Column("vendor", sa.String(length=255), nullable=True),
        sa.Column("part_number", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_case_component_items_id", "case_component_items", ["id"])
    op.create_index("ix_case_component_items_case_id", "case_component_items", ["case_id"])
    op.create_index("ix_case_component_items_module_id", "case_component_items", ["module_id"])
    op.create_index("ix_case_component_items_category", "case_component_items", ["category"])
    op.create_index("ix_case_component_items_owned", "case_component_items", ["owned"])
    op.create_index("ix_case_component_items_procurement_status", "case_component_items", ["procurement_status"])
    op.create_index("ix_case_component_items_source", "case_component_items", ["source"])


def downgrade() -> None:
    op.drop_table("case_component_items")
    op.drop_table("case_module_files")
    op.drop_table("case_modules")
