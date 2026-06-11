"""Add pgvector chunk vector table.

Revision ID: 20260602_0005
Revises: 20260523_0004
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa


revision = "20260602_0005"
down_revision = "20260523_0004"
branch_labels = None
depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("""
            CREATE TABLE knowledge_chunk_vectors (
                chunk_id INTEGER PRIMARY KEY REFERENCES knowledge_chunks(id) ON DELETE CASCADE,
                source_id INTEGER NOT NULL,
                case_id INTEGER,
                source_type VARCHAR(50) NOT NULL,
                embedding_model VARCHAR(255),
                embedding vector(384) NOT NULL
            )
        """)
        op.execute("CREATE INDEX ix_kcv_source_id ON knowledge_chunk_vectors(source_id)")
        op.execute("CREATE INDEX ix_kcv_case_id ON knowledge_chunk_vectors(case_id)")
        op.execute("CREATE INDEX ix_kcv_source_type ON knowledge_chunk_vectors(source_type)")
        op.execute("""
            CREATE INDEX ix_kcv_embedding_hnsw
            ON knowledge_chunk_vectors
            USING hnsw (embedding vector_cosine_ops)
        """)
        return

    op.create_table(
        "knowledge_chunk_vectors",
        sa.Column("chunk_id", sa.Integer(), sa.ForeignKey("knowledge_chunks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("source_id", sa.Integer(), nullable=False, index=True),
        sa.Column("case_id", sa.Integer(), nullable=True, index=True),
        sa.Column("source_type", sa.String(length=50), nullable=False, index=True),
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
        sa.Column("embedding", sa.Text(), nullable=False),
    )

def downgrade():
    op.drop_table("knowledge_chunk_vectors")
