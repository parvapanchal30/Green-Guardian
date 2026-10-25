"""actions: work done to assets (ADR-059)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-23

Expand-only: one new table, `actions`, append-only (trigger on PostgreSQL) with deny-by-default row-level security and
composite (workspace_id, ...) foreign keys to the asset, the issue, the task it was recorded for, the follow-up task it
scheduled, and the record it corrects. A partial unique index allows a record to be superseded at most once.
No existing table or data is touched. Downgrade drops the table.
"""

import sqlalchemy as sa
from alembic import op

from app.core import append_only, rls

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

KINDS = "'treat', 'water', 'fertilize', 'prune', 'pest_control', 'weed', 'mulch', 'replant', 'other'"
UNITS = "'l', 'ml', 'kg', 'g', 'count'"


def upgrade() -> None:
    op.create_table(
        "actions",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("issue_id", sa.Uuid()),
        sa.Column("task_id", sa.Uuid()),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("product", sa.String(120)),
        sa.Column("quantity", sa.Float()),
        sa.Column("unit", sa.String(8)),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("performed_by", sa.Uuid()),
        sa.Column("note", sa.Text()),
        sa.Column("follow_up_task_id", sa.Uuid()),
        sa.Column("supersedes_id", sa.Uuid()),
        sa.Column("withdrawn", sa.Boolean(), nullable=False),
        sa.Column("recorded_by", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(f"kind IN ({KINDS})", name=op.f("ck_actions_kind")),
        sa.CheckConstraint(f"unit IS NULL OR unit IN ({UNITS})", name=op.f("ck_actions_unit")),
        sa.CheckConstraint("(quantity IS NULL) = (unit IS NULL)", name=op.f("ck_actions_quantity_has_unit")),
        sa.CheckConstraint("quantity IS NULL OR quantity > 0", name=op.f("ck_actions_quantity_positive")),
        sa.CheckConstraint(
            "supersedes_id IS NULL OR (note IS NOT NULL AND length(note) >= 10)",
            name=op.f("ck_actions_correction_has_reason"),
        ),
        sa.CheckConstraint(
            "NOT withdrawn OR supersedes_id IS NOT NULL", name=op.f("ck_actions_withdrawal_is_correction")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], name=op.f("fk_actions_workspace_id_workspaces"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["biological_assets.workspace_id", "biological_assets.id"],
            name="fk_actions_asset",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "issue_id"],
            ["issues.workspace_id", "issues.id"],
            name="fk_actions_issue",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], name="fk_actions_task", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "follow_up_task_id"],
            ["tasks.workspace_id", "tasks.id"],
            name="fk_actions_follow_up_task",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "supersedes_id"],
            ["actions.workspace_id", "actions.id"],
            name="fk_actions_supersedes",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["performed_by"], ["users.id"], name=op.f("fk_actions_performed_by_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"], ["users.id"], name=op.f("fk_actions_recorded_by_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_actions")),
        sa.UniqueConstraint("workspace_id", "id", name="uq_actions_workspace_id_id"),
    )
    op.create_index("ix_actions_asset_performed", "actions", ["workspace_id", "asset_id", "performed_at"])
    op.create_index("ix_actions_issue", "actions", ["workspace_id", "issue_id"])
    op.create_index(
        "uq_actions_supersedes",
        "actions",
        ["workspace_id", "supersedes_id"],
        unique=True,
        postgresql_where=sa.text("supersedes_id IS NOT NULL"),
        sqlite_where=sa.text("supersedes_id IS NOT NULL"),
    )
    append_only.install_function()
    append_only.make_append_only("actions")
    rls.enable_rls("actions")


def downgrade() -> None:
    op.drop_table("actions")
