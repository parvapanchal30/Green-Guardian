"""asset lifecycle events (ADR-055)

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-22

Expand-only: one new table, `lifecycle_events`, append-only (trigger on PostgreSQL) with deny-by-default row-level
security and a composite (workspace_id, asset_id) foreign key, like every tenant history table.

Backfill: every existing asset gets ONE initial event carrying its current stage (source 'system', entered at its planting
date when known and not in the future, otherwise when it was registered), so the invariant "current_stage equals the
latest event" holds for old data too. The backfill runs before the append-only trigger is installed. Nothing in
`biological_assets` changes. Downgrade drops the table (the events are derived history; current_stage is untouched).
"""

import uuid
from datetime import UTC, date, datetime, time

import sqlalchemy as sa
from alembic import op

from app.core import append_only, rls
from app.core.ids import uuid7

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

STAGES = (
    "planted",
    "growing",
    "mature",
    "maintained",
    "health_monitoring",
    "survival",
    "germination",
    "vegetative",
    "flowering",
    "fruiting",
    "harvest",
    "post_harvest",
    "dead",
    "failed",
    "removed",
    "replaced",
)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _uid(value) -> uuid.UUID | None:
    """Raw SQL returns UUIDs as objects on PostgreSQL and as hex strings on SQLite."""
    return None if value is None else (value if isinstance(value, uuid.UUID) else uuid.UUID(str(value)))


def upgrade() -> None:
    op.create_table(
        "lifecycle_events",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("previous_stage", sa.String(32)),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("correction", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("actor_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "stage IN (" + ", ".join(repr(s) for s in STAGES) + ")", name=op.f("ck_lifecycle_events_stage")
        ),
        sa.CheckConstraint("source IN ('manual', 'system')", name=op.f("ck_lifecycle_events_source")),
        sa.CheckConstraint(
            "NOT correction OR (note IS NOT NULL AND length(note) >= 10)",
            name=op.f("ck_lifecycle_events_correction_has_reason"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_lifecycle_events_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["biological_assets.workspace_id", "biological_assets.id"],
            name="fk_lifecycle_events_asset",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_lifecycle_events_actor_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lifecycle_events")),
    )
    op.create_index("ix_lifecycle_events_asset_entered", "lifecycle_events", ["workspace_id", "asset_id", "entered_at"])

    bind = op.get_bind()
    assets = bind.execute(
        sa.text("SELECT id, workspace_id, current_stage, planted_at, created_at, created_by FROM biological_assets")
    ).all()
    events = sa.table(
        "lifecycle_events",
        sa.column("id", sa.Uuid()),
        sa.column("workspace_id", sa.Uuid()),
        sa.column("asset_id", sa.Uuid()),
        sa.column("stage", sa.String()),
        sa.column("previous_stage", sa.String()),
        sa.column("entered_at", sa.DateTime(timezone=True)),
        sa.column("source", sa.String()),
        sa.column("correction", sa.Boolean()),
        sa.column("note", sa.Text()),
        sa.column("actor_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    rows = []
    for asset_id, workspace_id, stage, planted_at, created_at, created_by in assets:
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        registered = _as_utc(created_at) if isinstance(created_at, datetime) else now
        entered = registered
        if planted_at is not None:
            planted = planted_at if isinstance(planted_at, date) else date.fromisoformat(str(planted_at)[:10])
            candidate = datetime.combine(planted, time.min, tzinfo=UTC)
            entered = min(candidate, registered)
        rows.append(
            {
                "id": uuid7(),
                "workspace_id": _uid(workspace_id),
                "asset_id": _uid(asset_id),
                "stage": stage if stage in STAGES else "planted",
                "previous_stage": None,
                "entered_at": entered,
                "source": "system",
                "correction": False,
                "note": "Initial stage (recorded when lifecycle history was introduced)",
                "actor_id": _uid(created_by),
                "created_at": now,
            }
        )
    for i in range(0, len(rows), 500):
        op.bulk_insert(events, rows[i : i + 500])

    append_only.install_function()
    append_only.make_append_only("lifecycle_events")
    rls.enable_rls("lifecycle_events")


def downgrade() -> None:
    op.drop_table("lifecycle_events")
