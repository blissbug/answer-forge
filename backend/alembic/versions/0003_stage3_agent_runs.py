"""Create Stage 3 agent runs and generation workflow states."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_stage3"
down_revision = "0002_stage2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE questionworkflowstatus ADD VALUE IF NOT EXISTS 'QUEUED'")
    op.execute("ALTER TYPE questionworkflowstatus ADD VALUE IF NOT EXISTS 'PROCESSING'")
    run_status = sa.Enum("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", name="agentrunstatus")
    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("questions.id"), nullable=False),
        sa.Column("answer_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("answer_versions.id")),
        sa.Column("status", run_status, nullable=False),
        sa.Column("model_provider", sa.String(128)), sa.Column("model_name", sa.String(256)),
        sa.Column("retrieval_rounds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_tokens", sa.Integer()), sa.Column("completion_tokens", sa.Integer()), sa.Column("estimated_cost", sa.Float()), sa.Column("latency_ms", sa.Integer()),
        sa.Column("error_type", sa.String(128)), sa.Column("error_message", sa.Text()), sa.Column("trace_data", postgresql.JSONB()), sa.Column("feedback", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_runs_question_id", "agent_runs", ["question_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.execute("CREATE UNIQUE INDEX uq_agent_runs_one_active_question ON agent_runs (question_id) WHERE status IN ('QUEUED', 'RUNNING')")


def downgrade() -> None:
    op.drop_table("agent_runs")
    sa.Enum(name="agentrunstatus").drop(op.get_bind(), checkfirst=True)
