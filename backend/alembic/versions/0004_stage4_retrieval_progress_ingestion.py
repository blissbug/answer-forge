"""Add hybrid retrieval indexes, workflow progress, and asynchronous ingestion runs."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0004_stage4"
down_revision = "0003_stage3"
branch_labels = None
depends_on = None


agent_phase = postgresql.ENUM(
    "QUEUED", "RETRIEVING", "ASSESSING", "DRAFTING", "VERIFYING", "REVISING", "PERSISTING", "READY_FOR_REVIEW", "FAILED",
    name="agentrunphase", create_type=False,
)
ingestion_status = postgresql.ENUM("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", name="ingestionrunstatus", create_type=False)
ingestion_phase = postgresql.ENUM("QUEUED", "PARSING", "CHUNKING", "EMBEDDING", "PERSISTING", "READY", "FAILED", name="ingestionphase", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    agent_phase.create(bind, checkfirst=True)
    ingestion_status.create(bind, checkfirst=True)
    ingestion_phase.create(bind, checkfirst=True)

    op.add_column("documents", sa.Column("source_type", sa.String(length=32), nullable=False, server_default="upload"))
    op.add_column("documents", sa.Column("department", sa.String(length=100), nullable=True))
    op.add_column("documents", sa.Column("document_type", sa.String(length=100), nullable=True))
    op.add_column("documents", sa.Column("effective_date", sa.Date(), nullable=True))
    op.create_index("ix_documents_workspace_source", "documents", ["workspace_id", "source_type"])
    op.create_index("ix_documents_workspace_department", "documents", ["workspace_id", "department"])
    op.create_index("ix_documents_workspace_document_type", "documents", ["workspace_id", "document_type"])
    op.create_index("ix_documents_workspace_effective_date", "documents", ["workspace_id", "effective_date"])
    op.alter_column("documents", "source_type", server_default=None)

    op.add_column("agent_runs", sa.Column("phase", agent_phase, nullable=False, server_default="QUEUED"))
    op.add_column("agent_runs", sa.Column("progress_message", sa.String(length=255), nullable=True))
    op.add_column("agent_runs", sa.Column("trace_id", sa.String(length=32), nullable=True))
    op.add_column("agent_runs", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.execute("UPDATE agent_runs SET phase = (CASE WHEN status = 'SUCCEEDED' THEN 'READY_FOR_REVIEW' WHEN status = 'FAILED' THEN 'FAILED' ELSE 'QUEUED' END)::agentrunphase")
    op.alter_column("agent_runs", "phase", server_default=None)

    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("status", ingestion_status, nullable=False, server_default="QUEUED"),
        sa.Column("phase", ingestion_phase, nullable=False, server_default="QUEUED"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("processed_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_chunks", sa.Integer()),
        sa.Column("error_type", sa.String(length=128)),
        sa.Column("error_message", sa.Text()),
        sa.Column("trace_id", sa.String(length=32)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ingestion_runs_document_id", "ingestion_runs", ["document_id"])
    op.create_index("ix_ingestion_runs_status", "ingestion_runs", ["status"])
    op.execute("CREATE UNIQUE INDEX uq_ingestion_runs_one_active_document ON ingestion_runs (document_id) WHERE status IN ('QUEUED', 'RUNNING')")

    with op.get_context().autocommit_block():
        op.execute("CREATE INDEX CONCURRENTLY ix_document_chunks_content_fts ON document_chunks USING gin (to_tsvector('english', content))")
        op.execute("CREATE INDEX CONCURRENTLY ix_document_chunks_embedding_hnsw_cosine ON document_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_document_chunks_embedding_hnsw_cosine")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_document_chunks_content_fts")

    op.drop_table("ingestion_runs")
    op.drop_index("ix_documents_workspace_effective_date", table_name="documents")
    op.drop_index("ix_documents_workspace_document_type", table_name="documents")
    op.drop_index("ix_documents_workspace_department", table_name="documents")
    op.drop_index("ix_documents_workspace_source", table_name="documents")
    op.drop_column("documents", "effective_date")
    op.drop_column("documents", "document_type")
    op.drop_column("documents", "department")
    op.drop_column("documents", "source_type")
    op.drop_column("agent_runs", "updated_at")
    op.drop_column("agent_runs", "trace_id")
    op.drop_column("agent_runs", "progress_message")
    op.drop_column("agent_runs", "phase")

    bind = op.get_bind()
    ingestion_phase.drop(bind, checkfirst=True)
    ingestion_status.drop(bind, checkfirst=True)
    agent_phase.drop(bind, checkfirst=True)
