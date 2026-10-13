"""Create Stage 1 knowledge base tables."""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0001_stage1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    status = sa.Enum("UPLOADED", "PROCESSING", "READY", "FAILED", name="documentstatus")
    op.create_table("users", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("name", sa.String(255), nullable=False))
    op.create_table("workspaces", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("name", sa.String(255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False))
    op.create_table("documents", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False), sa.Column("filename", sa.String(512), nullable=False), sa.Column("storage_path", sa.String(1024), nullable=False), sa.Column("status", status, nullable=False), sa.Column("notes", sa.Text()), sa.Column("metadata", postgresql.JSONB(), nullable=False), sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("deleted_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_documents_workspace_id", "documents", ["workspace_id"])
    op.create_index("ix_documents_is_deleted", "documents", ["is_deleted"])
    op.create_table("document_pages", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False), sa.Column("page_number", sa.Integer(), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("metadata", postgresql.JSONB(), nullable=False), sa.UniqueConstraint("document_id", "page_number", name="uq_document_page"))
    op.create_index("ix_document_pages_document_id", "document_pages", ["document_id"])
    op.create_table("document_chunks", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False), sa.Column("chunk_index", sa.Integer(), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("embedding", Vector(dim=1536), nullable=False), sa.Column("metadata", postgresql.JSONB(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"))
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])


def downgrade() -> None:
    op.drop_table("document_chunks")
    op.drop_table("document_pages")
    op.drop_table("documents")
    op.drop_table("workspaces")
    op.drop_table("users")
    sa.Enum(name="documentstatus").drop(op.get_bind(), checkfirst=True)
