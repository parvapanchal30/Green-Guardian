"""agent runs and recommendation traceability / outcomes

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-18

Stage C (scheduled Botanical Operations Agent). Backward compatible (expand only): a new table and nullable columns.

  * agent_runs: execution history of manual and scheduled runs. A partial unique index allows only one `running` row per
    workspace, which is what stops overlapping runs across processes.
  * recommendations: which run produced it, the rule version, and (later) the outcome of the work it led to.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core import rls

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("worker_id", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluated_assets", sa.Integer(), nullable=False),
        sa.Column("findings", sa.Integer(), nullable=False),
        sa.Column("recommendations_created", sa.Integer(), nullable=False),
        sa.Column("recommendations_expired", sa.Integer(), nullable=False),
        sa.Column("rules", JSON, nullable=False),
        sa.Column("diagnostics", JSON, nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("trigger IN ('manual', 'scheduled')", name=op.f("ck_agent_runs_trigger")),
        sa.CheckConstraint("status IN ('running', 'succeeded', 'failed')", name=op.f("ck_agent_runs_status")),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["users.id"], name=op.f("fk_agent_runs_requested_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], name=op.f("fk_agent_runs_workspace_id_workspaces"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
        sa.UniqueConstraint("workspace_id", "id", name="uq_agent_runs_workspace_id_id"),
    )
    op.create_index("ix_agent_runs_workspace_started", "agent_runs", ["workspace_id", "started_at"], unique=False)
    op.create_index(
        "uq_agent_runs_one_running",
        "agent_runs",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
        sqlite_where=sa.text("status = 'running'"),
    )

    with op.batch_alter_table("recommendations") as batch:
        batch.add_column(sa.Column("agent_run_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("rule_version", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("outcome", sa.String(length=24), nullable=True))
        batch.add_column(sa.Column("outcome_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("outcome_detail", sa.Text(), nullable=True))
        batch.create_foreign_key(
            "fk_recommendations_agent_run",
            "agent_runs",
            ["workspace_id", "agent_run_id"],
            ["workspace_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            op.f("ck_recommendations_outcome"),
            "outcome IS NULL OR outcome IN ('task_completed', 'task_cancelled', 'issue_resolved', 'issue_closed', "
            "'deferral_applied')",
        )
    rls.enable_rls("agent_runs")


def downgrade() -> None:
    with op.batch_alter_table("recommendations") as batch:
        batch.drop_constraint(op.f("ck_recommendations_outcome"), type_="check")
        batch.drop_constraint("fk_recommendations_agent_run", type_="foreignkey")
        batch.drop_column("outcome_detail")
        batch.drop_column("outcome_at")
        batch.drop_column("outcome")
        batch.drop_column("rule_version")
        batch.drop_column("agent_run_id")
    op.drop_index("uq_agent_runs_one_running", table_name="agent_runs")
    op.drop_index("ix_agent_runs_workspace_started", table_name="agent_runs")
    op.drop_table("agent_runs")
