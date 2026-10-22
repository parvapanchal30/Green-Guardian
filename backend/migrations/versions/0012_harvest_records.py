"""harvest records (ADR-056)

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-22

Expand-only: one new table, `harvest_records`, append-only (trigger on PostgreSQL) with deny-by-default row-level security,
a composite (workspace_id, asset_id) foreign key like every tenant history table, and a self-reference
(workspace_id, supersedes_id) for corrections. A partial unique index allows a record to be superseded at most once.
No existing table or data is touched. Downgrade drops the table.
"""

import sqlalchemy as sa
from alembic import op

from app.core import append_only, rls

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "harvest_records",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("harvested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(8), nullable=False),
        sa.Column("grade", sa.String(40)),
        sa.Column("note", sa.Text()),
        sa.Column("supersedes_id", sa.Uuid()),
        sa.Column("recorded_by", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("unit IN ('kg', 't', 'count', 'l')", name=op.f("ck_harvest_records_unit")),
        sa.CheckConstraint("quantity >= 0", name=op.f("ck_harvest_records_quantity_nonnegative")),
        sa.CheckConstraint(
            "supersedes_id IS NOT NULL OR quantity > 0", name=op.f("ck_harvest_records_new_record_positive")
        ),
        sa.CheckConstraint(
            "supersedes_id IS NULL OR (note IS NOT NULL AND length(note) >= 10)",
            name=op.f("ck_harvest_records_correction_has_reason"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_harvest_records_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["biological_assets.workspace_id", "biological_assets.id"],
            name="fk_harvest_records_asset",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "supersedes_id"],
            ["harvest_records.workspace_id", "harvest_records.id"],
            name="fk_harvest_records_supersedes",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"], ["users.id"], name=op.f("fk_harvest_records_recorded_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_harvest_records")),
        sa.UniqueConstraint("workspace_id", "id", name="uq_harvest_records_workspace_id_id"),
    )
    op.create_index(
        "ix_harvest_records_asset_harvested", "harvest_records", ["workspace_id", "asset_id", "harvested_at"]
    )
    op.create_index(
        "uq_harvest_records_supersedes",
        "harvest_records",
        ["workspace_id", "supersedes_id"],
        unique=True,
        postgresql_where=sa.text("supersedes_id IS NOT NULL"),
        sqlite_where=sa.text("supersedes_id IS NOT NULL"),
    )
    append_only.install_function()
    append_only.make_append_only("harvest_records")
    rls.enable_rls("harvest_records")


def downgrade() -> None:
    op.drop_table("harvest_records")
