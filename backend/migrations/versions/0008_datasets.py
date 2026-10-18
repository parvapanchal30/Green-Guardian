"""dataset catalog, label review and versioned splits (Stage D)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-18

Expand-only: six new tables, no existing table is touched. Evidence, approval history, label reviews and splits are
append-only (database trigger on PostgreSQL), and every table has deny-by-default row-level security.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core import append_only, rls

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
WS = "workspaces.id"
STATUSES = "'proposed', 'under_review', 'approved', 'rejected'"
LABELS = "'unreviewed', 'under_review', 'accepted', 'rejected', 'corrected'"


def _fk_ws(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["workspace_id"], [WS], name=op.f(f"fk_{table}_workspace_id_workspaces"), ondelete="CASCADE"
    )


def _fk_user(table: str, col: str, ondelete: str = "SET NULL") -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([col], ["users.id"], name=op.f(f"fk_{table}_{col}_users"), ondelete=ondelete)


def _fk_dataset(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["workspace_id", "dataset_id"],
        ["datasets.workspace_id", "datasets.id"],
        name=f"fk_{table}_dataset",
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("accessed_at", sa.DateTime(timezone=True)),
        sa.Column("licence_spdx", sa.String(60), nullable=False),
        sa.Column("images_licence_spdx", sa.String(60), nullable=False),
        sa.Column("annotations_licence_spdx", sa.String(60)),
        sa.Column("has_annotations", sa.Boolean(), nullable=False),
        sa.Column("attribution_required", sa.Boolean()),
        sa.Column("attribution_text", sa.Text()),
        sa.Column("commercial_use", sa.String(8), nullable=False),
        sa.Column("redistribution", sa.String(8), nullable=False),
        sa.Column("intended_use", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by", sa.Uuid()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("kind IN ('real', 'synthetic')", name=op.f("ck_datasets_kind")),
        sa.CheckConstraint(f"status IN ({STATUSES})", name=op.f("ck_datasets_status")),
        sa.CheckConstraint("commercial_use IN ('yes', 'no', 'unknown')", name=op.f("ck_datasets_commercial_use")),
        sa.CheckConstraint("redistribution IN ('yes', 'no', 'unknown')", name=op.f("ck_datasets_redistribution")),
        sa.CheckConstraint(
            "status <> 'approved' OR kind = 'synthetic' OR approved_by IS NOT NULL",
            name=op.f("ck_datasets_approved_by"),
        ),
        _fk_ws("datasets"),
        _fk_user("datasets", "created_by"),
        _fk_user("datasets", "approved_by"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
        sa.UniqueConstraint("workspace_id", "id", name="uq_datasets_workspace_id_id"),
        sa.UniqueConstraint("workspace_id", "name", "version", name="uq_datasets_name_version"),
    )
    op.create_table(
        "dataset_evidence",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("scope", sa.String(12), nullable=False),
        sa.Column("licence_spdx", sa.String(60), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("official", sa.Boolean(), nullable=False),
        sa.Column("accessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.Uuid()),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("scope IN ('images', 'annotations', 'both')", name=op.f("ck_dataset_evidence_scope")),
        _fk_ws("dataset_evidence"),
        _fk_user("dataset_evidence", "recorded_by"),
        _fk_dataset("dataset_evidence"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_evidence")),
    )
    op.create_index("ix_dataset_evidence_dataset", "dataset_evidence", ["dataset_id"])
    op.create_table(
        "dataset_status_history",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(16)),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.Uuid()),
        sa.Column("note", sa.Text()),
        sa.Column("blockers", JSON, nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        _fk_ws("dataset_status_history"),
        _fk_user("dataset_status_history", "actor_id"),
        _fk_dataset("dataset_status_history"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_status_history")),
    )
    op.create_index("ix_dataset_status_history_dataset_at", "dataset_status_history", ["dataset_id", "at"])
    op.create_table(
        "dataset_samples",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(300), nullable=False),
        sa.Column("group_key", sa.String(200)),
        sa.Column("label", sa.String(120)),
        sa.Column("label_status", sa.String(16), nullable=False),
        sa.Column("content_sha256", sa.String(64)),
        sa.Column("phash", sa.String(16)),
        sa.Column("file_status", sa.String(8)),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("provenance", JSON, nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(f"label_status IN ({LABELS})", name=op.f("ck_dataset_samples_label_status")),
        sa.CheckConstraint(
            "file_status IS NULL OR file_status IN ('ok', 'invalid')", name=op.f("ck_dataset_samples_file_status")
        ),
        _fk_ws("dataset_samples"),
        _fk_dataset("dataset_samples"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_samples")),
        sa.UniqueConstraint("workspace_id", "id", name="uq_dataset_samples_workspace_id_id"),
        sa.UniqueConstraint("dataset_id", "external_id", name="uq_dataset_samples_external"),
    )
    op.create_index("ix_dataset_samples_dataset_status", "dataset_samples", ["dataset_id", "label_status"])
    op.create_table(
        "label_reviews",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("sample_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_qualification", sa.String(300)),
        sa.Column("from_status", sa.String(16), nullable=False),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("from_label", sa.String(120)),
        sa.Column("to_label", sa.String(120)),
        sa.Column("evidence", sa.Text()),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        _fk_ws("label_reviews"),
        _fk_user("label_reviews", "reviewer_id", "RESTRICT"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "sample_id"],
            ["dataset_samples.workspace_id", "dataset_samples.id"],
            name="fk_label_reviews_sample",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_label_reviews")),
    )
    op.create_index("ix_label_reviews_sample_at", "label_reviews", ["sample_id", "at"])
    op.create_table(
        "dataset_splits",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("fractions", JSON, nullable=False),
        sa.Column("include_unreviewed", sa.Boolean(), nullable=False),
        sa.Column("manifest", JSON, nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("stats", JSON, nullable=False),
        sa.Column("warnings", JSON, nullable=False),
        sa.Column("leakage_violations", JSON, nullable=False),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        _fk_ws("dataset_splits"),
        _fk_user("dataset_splits", "created_by"),
        _fk_dataset("dataset_splits"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_splits")),
        sa.UniqueConstraint("dataset_id", "version", name="uq_dataset_splits_version"),
    )
    append_only.install_function()
    for t in ("dataset_evidence", "dataset_status_history", "label_reviews", "dataset_splits"):
        append_only.make_append_only(t)
    for t in (
        "datasets",
        "dataset_evidence",
        "dataset_status_history",
        "dataset_samples",
        "label_reviews",
        "dataset_splits",
    ):
        rls.enable_rls(t)


def downgrade() -> None:
    for t in (
        "dataset_splits",
        "label_reviews",
        "dataset_samples",
        "dataset_status_history",
        "dataset_evidence",
        "datasets",
    ):
        op.drop_table(t)
