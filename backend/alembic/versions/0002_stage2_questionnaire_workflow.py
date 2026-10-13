"""Create Stage 2 questionnaire workflow tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_stage2"
down_revision = "0001_stage1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    questionnaire_status = sa.Enum("UPLOADED", "PARSING", "READY", "IN_REVIEW", "COMPLETED", "FAILED", name="questionnairestatus")
    question_status = sa.Enum("EXTRACTED", "READY_FOR_REVIEW", "APPROVED", "REJECTED", "NOT_APPLICABLE", "FAILED", name="questionworkflowstatus")
    answer_origin = sa.Enum("MANUAL", "EDITED", "IMPORTED", "AGENT", name="answerorigin")
    evidence_status = sa.Enum("STRONG", "PARTIAL", "CONFLICTING", "MISSING", name="evidencestatus")
    op.create_table("questionnaires", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False), sa.Column("title", sa.String(512), nullable=False), sa.Column("status", questionnaire_status, nullable=False), sa.Column("question_column", sa.String(255), nullable=False), sa.Column("answer_column", sa.String(255), nullable=False), sa.Column("context", sa.Text()), sa.Column("storage_path", sa.String(1024), nullable=False), sa.Column("original_filename", sa.String(512), nullable=False), sa.Column("source_format", sa.String(16), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_questionnaires_workspace_id", "questionnaires", ["workspace_id"])
    op.create_table("questions", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("questionnaire_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("questionnaires.id"), nullable=False), sa.Column("question_text", sa.Text(), nullable=False), sa.Column("workflow_status", question_status, nullable=False), sa.Column("position", sa.Integer(), nullable=False), sa.Column("original_row", sa.Integer(), nullable=False), sa.Column("source_row", postgresql.JSONB(), nullable=False), sa.Column("not_applicable_reason", sa.Text()), sa.Column("current_answer_version_id", postgresql.UUID(as_uuid=True), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("questionnaire_id", "position", name="uq_question_position"))
    op.create_index("ix_questions_questionnaire_id", "questions", ["questionnaire_id"])
    op.create_index("ix_questions_workflow_status", "questions", ["workflow_status"])
    op.create_table("answer_versions", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("questions.id"), nullable=False), sa.Column("version_number", sa.Integer(), nullable=False), sa.Column("answer_text", sa.Text(), nullable=False), sa.Column("evidence_status", evidence_status, nullable=False), sa.Column("origin", answer_origin, nullable=False), sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("question_id", "version_number", name="uq_answer_version_number"))
    op.create_index("ix_answer_versions_question_id", "answer_versions", ["question_id"])
    op.create_foreign_key("fk_question_current_answer", "questions", "answer_versions", ["current_answer_version_id"], ["id"])
    op.create_table("citations", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("answer_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("answer_versions.id"), nullable=False), sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False), sa.Column("document_chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True), sa.Column("quoted_text", sa.Text(), nullable=False), sa.Column("page_number", sa.Integer()), sa.Column("section_title", sa.String(512)), sa.Column("relevance_score", sa.Float()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_citations_answer_version_id", "citations", ["answer_version_id"])
    op.create_index("ix_citations_document_id", "citations", ["document_id"])


def downgrade() -> None:
    op.drop_table("citations")
    op.drop_constraint("fk_question_current_answer", "questions", type_="foreignkey")
    op.drop_table("answer_versions")
    op.drop_table("questions")
    op.drop_table("questionnaires")
    for name in ("evidencestatus", "answerorigin", "questionworkflowstatus", "questionnairestatus"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
