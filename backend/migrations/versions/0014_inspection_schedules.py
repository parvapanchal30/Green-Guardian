"""recurring inspection schedules (ADR-062)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-25

Expand-only: two new tables. `inspection_schedules` is configuration (editable, every change audited) with
deny-by-default row-level security and composite (workspace_id, ...) foreign keys to the asset or the location it covers.
`schedule_occurrences` is append-only (trigger on PostgreSQL): one row per due date reached, with a unique
(workspace_id, schedule_id, due_at) key that makes task generation idempotent. No existing table or data is touched.
Downgrade drops both tables.
"""

import sqlalchemy as sa
from alembic import op

from app.core import append_only, rls

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inspection_schedules",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid()),
        sa.Column("location_id", sa.Uuid()),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("task_type", sa.String(16), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("lead_days", sa.Integer(), nullable=False),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assignee_id", sa.Uuid()),
        sa.Column("priority", sa.String(2), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "(asset_id IS NULL) <> (location_id IS NULL)", name=op.f("ck_inspection_schedules_one_subject")
        ),
        sa.CheckConstraint("task_type IN ('inspect', 'monitor')", name=op.f("ck_inspection_schedules_task_type")),
        sa.CheckConstraint("interval_days BETWEEN 1 AND 365", name=op.f("ck_inspection_schedules_interval_days")),
        sa.CheckConstraint(
            "lead_days BETWEEN 0 AND 30 AND lead_days < interval_days", name=op.f("ck_inspection_schedules_lead_days")
        ),
        sa.CheckConstraint("priority IN ('p1', 'p2', 'p3', 'p4')", name=op.f("ck_inspection_schedules_priority")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_inspection_schedules_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["biological_assets.workspace_id", "biological_assets.id"],
            name="fk_inspection_schedules_asset",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "location_id"],
            ["locations.workspace_id", "locations.id"],
            name="fk_inspection_schedules_location",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"], ["users.id"], name=op.f("fk_inspection_schedules_assignee_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_inspection_schedules_created_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inspection_schedules")),
        sa.UniqueConstraint("workspace_id", "id", name="uq_inspection_schedules_workspace_id_id"),
    )
    op.create_index("ix_inspection_schedules_due", "inspection_schedules", ["active", "next_due_at"])
    op.create_index("ix_inspection_schedules_asset", "inspection_schedules", ["workspace_id", "asset_id"])

    op.create_table(
        "schedule_occurrences",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("task_id", sa.Uuid()),
        sa.Column("missed", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('created', 'skipped_open_task', 'skipped_inactive_asset')",
            name=op.f("ck_schedule_occurrences_outcome"),
        ),
        sa.CheckConstraint(
            "(outcome = 'created') = (task_id IS NOT NULL)", name=op.f("ck_schedule_occurrences_task_when_created")
        ),
        sa.CheckConstraint("missed >= 0", name=op.f("ck_schedule_occurrences_missed")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_schedule_occurrences_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "schedule_id"],
            ["inspection_schedules.workspace_id", "inspection_schedules.id"],
            name="fk_schedule_occurrences_schedule",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["tasks.workspace_id", "tasks.id"],
            name="fk_schedule_occurrences_task",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schedule_occurrences")),
        sa.UniqueConstraint("workspace_id", "schedule_id", "due_at", name="uq_schedule_occurrences_due"),
    )
    append_only.install_function()
    append_only.make_append_only("schedule_occurrences")
    rls.enable_rls("inspection_schedules")
    rls.enable_rls("schedule_occurrences")


def downgrade() -> None:
    op.drop_table("schedule_occurrences")
    op.drop_table("inspection_schedules")
