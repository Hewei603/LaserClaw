"""initial enterprise agent rag schema

Revision ID: 20260515_0001
Revises:
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa

revision = "20260515_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("organizations", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(255), nullable=False, unique=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_organizations_id", "organizations", ["id"])

    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id")), sa.Column("email", sa.String(255), nullable=False), sa.Column("display_name", sa.String(255), nullable=False), sa.Column("role", sa.String(50)), sa.Column("is_active", sa.Boolean()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_organization_id", "users", ["organization_id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table("experiment_cases", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("title", sa.String(255), nullable=False), sa.Column("description", sa.Text()), sa.Column("cavity_type", sa.String(50), nullable=False), sa.Column("goal", sa.Text(), nullable=False), sa.Column("parameters", sa.JSON()), sa.Column("symptoms", sa.JSON()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.create_index("ix_experiment_cases_id", "experiment_cases", ["id"])
    op.create_index("ix_experiment_cases_title", "experiment_cases", ["title"])

    op.create_table("attachments", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("case_id", sa.Integer(), sa.ForeignKey("experiment_cases.id"), nullable=False), sa.Column("filename", sa.String(255), nullable=False), sa.Column("filepath", sa.String(512), nullable=False), sa.Column("file_type", sa.String(100)), sa.Column("content_hash", sa.String(64)), sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_attachments_id", "attachments", ["id"])
    op.create_index("ix_attachments_case_id", "attachments", ["case_id"])
    op.create_index("ix_attachments_content_hash", "attachments", ["content_hash"])

    op.create_table("generated_contents", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("case_id", sa.Integer(), sa.ForeignKey("experiment_cases.id"), nullable=False), sa.Column("content_type", sa.String(50), nullable=False), sa.Column("content", sa.JSON(), nullable=False), sa.Column("model", sa.String(100)), sa.Column("prompt_version", sa.String(100)), sa.Column("input_tokens", sa.Integer()), sa.Column("output_tokens", sa.Integer()), sa.Column("latency_ms", sa.Integer()), sa.Column("cost_estimate", sa.String(50)), sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_generated_contents_id", "generated_contents", ["id"])
    op.create_index("ix_generated_contents_case_id", "generated_contents", ["case_id"])
    op.create_index("ix_generated_contents_content_type", "generated_contents", ["content_type"])

    op.create_table("agent_tasks", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("case_id", sa.Integer(), sa.ForeignKey("experiment_cases.id")), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("goal", sa.Text(), nullable=False), sa.Column("mode", sa.String(50)), sa.Column("status", sa.String(50)), sa.Column("risk_level", sa.String(50)), sa.Column("final_content_id", sa.Integer(), sa.ForeignKey("generated_contents.id")), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.create_index("ix_agent_tasks_id", "agent_tasks", ["id"])
    op.create_index("ix_agent_tasks_case_id", "agent_tasks", ["case_id"])
    op.create_index("ix_agent_tasks_user_id", "agent_tasks", ["user_id"])
    op.create_index("ix_agent_tasks_status", "agent_tasks", ["status"])

    op.create_table("agent_steps", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("task_id", sa.Integer(), sa.ForeignKey("agent_tasks.id"), nullable=False), sa.Column("step_index", sa.Integer(), nullable=False), sa.Column("title", sa.String(255), nullable=False), sa.Column("status", sa.String(50)), sa.Column("rationale", sa.Text()), sa.Column("result_summary", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.create_index("ix_agent_steps_id", "agent_steps", ["id"])
    op.create_index("ix_agent_steps_task_id", "agent_steps", ["task_id"])

    op.create_table("agent_tool_calls", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("task_id", sa.Integer(), sa.ForeignKey("agent_tasks.id"), nullable=False), sa.Column("step_id", sa.Integer(), sa.ForeignKey("agent_steps.id")), sa.Column("tool_name", sa.String(100), nullable=False), sa.Column("input_json", sa.JSON()), sa.Column("output_json", sa.JSON()), sa.Column("status", sa.String(50)), sa.Column("latency_ms", sa.Integer()), sa.Column("error_message", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_agent_tool_calls_id", "agent_tool_calls", ["id"])
    op.create_index("ix_agent_tool_calls_task_id", "agent_tool_calls", ["task_id"])
    op.create_index("ix_agent_tool_calls_step_id", "agent_tool_calls", ["step_id"])
    op.create_index("ix_agent_tool_calls_tool_name", "agent_tool_calls", ["tool_name"])

    op.create_table("knowledge_sources", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("case_id", sa.Integer(), sa.ForeignKey("experiment_cases.id")), sa.Column("attachment_id", sa.Integer(), sa.ForeignKey("attachments.id")), sa.Column("generated_content_id", sa.Integer(), sa.ForeignKey("generated_contents.id")), sa.Column("source_type", sa.String(50), nullable=False), sa.Column("title", sa.String(255), nullable=False), sa.Column("uri", sa.String(512)), sa.Column("content_hash", sa.String(64)), sa.Column("metadata_json", sa.JSON()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.create_index("ix_knowledge_sources_id", "knowledge_sources", ["id"])
    op.create_index("ix_knowledge_sources_case_id", "knowledge_sources", ["case_id"])
    op.create_index("ix_knowledge_sources_attachment_id", "knowledge_sources", ["attachment_id"])
    op.create_index("ix_knowledge_sources_generated_content_id", "knowledge_sources", ["generated_content_id"])
    op.create_index("ix_knowledge_sources_source_type", "knowledge_sources", ["source_type"])
    op.create_index("ix_knowledge_sources_content_hash", "knowledge_sources", ["content_hash"])

    op.create_table("knowledge_chunks", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("source_id", sa.Integer(), sa.ForeignKey("knowledge_sources.id"), nullable=False), sa.Column("chunk_index", sa.Integer(), nullable=False), sa.Column("text", sa.Text(), nullable=False), sa.Column("token_count", sa.Integer()), sa.Column("metadata_json", sa.JSON()), sa.Column("embedding", sa.JSON()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_knowledge_chunks_id", "knowledge_chunks", ["id"])
    op.create_index("ix_knowledge_chunks_source_id", "knowledge_chunks", ["source_id"])

    op.create_table("retrieval_runs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("task_id", sa.Integer(), sa.ForeignKey("agent_tasks.id")), sa.Column("query", sa.Text(), nullable=False), sa.Column("filters_json", sa.JSON()), sa.Column("top_k", sa.Integer()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_retrieval_runs_id", "retrieval_runs", ["id"])
    op.create_index("ix_retrieval_runs_task_id", "retrieval_runs", ["task_id"])

    op.create_table("retrieval_results", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("retrieval_run_id", sa.Integer(), sa.ForeignKey("retrieval_runs.id"), nullable=False), sa.Column("chunk_id", sa.Integer(), sa.ForeignKey("knowledge_chunks.id"), nullable=False), sa.Column("score", sa.Float(), nullable=False), sa.Column("rank", sa.Integer(), nullable=False))
    op.create_index("ix_retrieval_results_id", "retrieval_results", ["id"])
    op.create_index("ix_retrieval_results_retrieval_run_id", "retrieval_results", ["retrieval_run_id"])
    op.create_index("ix_retrieval_results_chunk_id", "retrieval_results", ["chunk_id"])

    op.create_table("audit_logs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer()), sa.Column("actor", sa.String(255)), sa.Column("action", sa.String(100), nullable=False), sa.Column("resource_type", sa.String(100), nullable=False), sa.Column("resource_id", sa.String(100)), sa.Column("request_id", sa.String(100)), sa.Column("metadata_json", sa.JSON()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_audit_logs_id", "audit_logs", ["id"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_resource_id", "audit_logs", ["resource_id"])
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])


def downgrade() -> None:
    for table in [
        "audit_logs",
        "retrieval_results",
        "retrieval_runs",
        "knowledge_chunks",
        "knowledge_sources",
        "agent_tool_calls",
        "agent_steps",
        "agent_tasks",
        "generated_contents",
        "attachments",
        "experiment_cases",
        "users",
        "organizations",
    ]:
        op.drop_table(table)
