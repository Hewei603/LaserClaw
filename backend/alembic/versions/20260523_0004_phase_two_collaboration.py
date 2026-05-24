"""phase two collaboration case governance versioning evals

Revision ID: 20260523_0004
Revises: 20260523_0003
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260523_0004"
down_revision = "20260523_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    def has_table(name: str) -> bool:
        return name in inspector.get_table_names()

    def columns(name: str) -> set[str]:
        return {column["name"] for column in inspector.get_columns(name)} if has_table(name) else set()

    def indexes(name: str) -> set[str]:
        return {index["name"] for index in inspector.get_indexes(name)} if has_table(name) else set()

    def create_index_once(name: str, table: str, cols: list[str]) -> None:
        if name not in indexes(table):
            op.create_index(name, table, cols)

    if not has_table("groups"):
        op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "name", name="uq_groups_org_name"),
        )
    create_index_once("ix_groups_id", "groups", ["id"])
    create_index_once("ix_groups_organization_id", "groups", ["organization_id"])
    create_index_once("ix_groups_name", "groups", ["name"])

    if not has_table("projects"):
        op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("organization_id", "name", name="uq_projects_org_name"),
        )
    create_index_once("ix_projects_id", "projects", ["id"])
    create_index_once("ix_projects_organization_id", "projects", ["organization_id"])
    create_index_once("ix_projects_name", "projects", ["name"])
    create_index_once("ix_projects_visibility", "projects", ["visibility"])

    if not has_table("group_members"):
        op.create_table(
        "group_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("group_id", "user_id", name="uq_group_members_group_user"),
        )
    create_index_once("ix_group_members_id", "group_members", ["id"])
    create_index_once("ix_group_members_group_id", "group_members", ["group_id"])
    create_index_once("ix_group_members_user_id", "group_members", ["user_id"])
    create_index_once("ix_group_members_role", "group_members", ["role"])

    if not has_table("project_members"):
        op.create_table(
        "project_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id"), nullable=True),
        sa.Column("role", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    create_index_once("ix_project_members_id", "project_members", ["id"])
    create_index_once("ix_project_members_project_id", "project_members", ["project_id"])
    create_index_once("ix_project_members_user_id", "project_members", ["user_id"])
    create_index_once("ix_project_members_group_id", "project_members", ["group_id"])
    create_index_once("ix_project_members_role", "project_members", ["role"])

    case_columns = columns("experiment_cases")
    for name, column_type in [
        ("project_id", sa.Integer()),
        ("status", sa.String(50)),
        ("visibility", sa.String(50)),
        ("schema_version", sa.String(50)),
        ("tags", sa.JSON()),
        ("measurements", sa.JSON()),
        ("safety_notes", sa.Text()),
        ("conclusions", sa.Text()),
        ("owner_id", sa.Integer()),
    ]:
        if name not in case_columns:
            op.add_column("experiment_cases", sa.Column(name, column_type, nullable=True))
    create_index_once("ix_experiment_cases_project_id", "experiment_cases", ["project_id"])
    create_index_once("ix_experiment_cases_status", "experiment_cases", ["status"])
    create_index_once("ix_experiment_cases_visibility", "experiment_cases", ["visibility"])
    create_index_once("ix_experiment_cases_owner_id", "experiment_cases", ["owner_id"])

    source_columns = columns("knowledge_sources")
    for name, column_type in [
        ("governance_status", sa.String(50)),
        ("version", sa.Integer()),
        ("owner_id", sa.Integer()),
        ("reviewed_by_id", sa.Integer()),
        ("reviewed_at", sa.DateTime(timezone=True)),
    ]:
        if name not in source_columns:
            op.add_column("knowledge_sources", sa.Column(name, column_type, nullable=True))
    create_index_once("ix_knowledge_sources_governance_status", "knowledge_sources", ["governance_status"])
    create_index_once("ix_knowledge_sources_owner_id", "knowledge_sources", ["owner_id"])

    if not has_table("prompt_versions"):
        op.create_table(
        "prompt_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("name", "version", name="uq_prompt_versions_name_version"),
        )
    create_index_once("ix_prompt_versions_id", "prompt_versions", ["id"])
    create_index_once("ix_prompt_versions_name", "prompt_versions", ["name"])
    create_index_once("ix_prompt_versions_version", "prompt_versions", ["version"])
    create_index_once("ix_prompt_versions_is_active", "prompt_versions", ["is_active"])

    if not has_table("workflow_versions"):
        op.create_table(
        "workflow_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("name", "version", name="uq_workflow_versions_name_version"),
        )
    create_index_once("ix_workflow_versions_id", "workflow_versions", ["id"])
    create_index_once("ix_workflow_versions_name", "workflow_versions", ["name"])
    create_index_once("ix_workflow_versions_version", "workflow_versions", ["version"])
    create_index_once("ix_workflow_versions_is_active", "workflow_versions", ["is_active"])

    if not has_table("rag_eval_runs"):
        op.create_table(
        "rag_eval_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("dataset", sa.JSON(), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=True),
        sa.Column("hit_rate", sa.Float(), nullable=True),
        sa.Column("mean_max_score", sa.Float(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    create_index_once("ix_rag_eval_runs_id", "rag_eval_runs", ["id"])
    create_index_once("ix_rag_eval_runs_name", "rag_eval_runs", ["name"])


def downgrade() -> None:
    op.drop_table("rag_eval_runs")
    op.drop_table("workflow_versions")
    op.drop_table("prompt_versions")
    op.drop_index("ix_knowledge_sources_owner_id", table_name="knowledge_sources")
    op.drop_index("ix_knowledge_sources_governance_status", table_name="knowledge_sources")
    for column in ["reviewed_at", "reviewed_by_id", "owner_id", "version", "governance_status"]:
        op.drop_column("knowledge_sources", column)
    for index in [
        "ix_experiment_cases_owner_id",
        "ix_experiment_cases_visibility",
        "ix_experiment_cases_status",
        "ix_experiment_cases_project_id",
    ]:
        op.drop_index(index, table_name="experiment_cases")
    for column in [
        "owner_id",
        "conclusions",
        "safety_notes",
        "measurements",
        "tags",
        "schema_version",
        "visibility",
        "status",
        "project_id",
    ]:
        op.drop_column("experiment_cases", column)
    op.drop_table("project_members")
    op.drop_table("group_members")
    op.drop_table("projects")
    op.drop_table("groups")
