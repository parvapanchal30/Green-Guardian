"""evidence: stored images linked to assets, observations and issues

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17 14:00:52.851203
"""

import sqlalchemy as sa
from alembic import op

from app.core import rls

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=True),
        sa.Column("issue_id", sa.Uuid(), nullable=True),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(length=200), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp')", name=op.f("ck_evidence_content_type")
        ),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_evidence_size_positive")),
        sa.CheckConstraint("width > 0 AND height > 0", name=op.f("ck_evidence_dimensions_positive")),
        sa.ForeignKeyConstraint(
            ["deleted_by"], ["users.id"], name=op.f("fk_evidence_deleted_by_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"], ["users.id"], name=op.f("fk_evidence_uploaded_by_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["biological_assets.workspace_id", "biological_assets.id"],
            name="fk_evidence_asset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "issue_id"],
            ["issues.workspace_id", "issues.id"],
            name="fk_evidence_issue",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "observation_id"],
            ["observations.workspace_id", "observations.id"],
            name="fk_evidence_observation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], name=op.f("fk_evidence_workspace_id_workspaces"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence")),
        sa.UniqueConstraint("storage_key", name="uq_evidence_storage_key"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_evidence_workspace_id_id"),
    )
    op.create_index("ix_evidence_asset_created", "evidence", ["workspace_id", "asset_id", "created_at"], unique=False)
    op.create_index("ix_evidence_issue", "evidence", ["workspace_id", "issue_id"], unique=False)
    op.create_index("ix_evidence_observation", "evidence", ["workspace_id", "observation_id"], unique=False)
    rls.enable_rls("evidence")  # deny-by-default, like every application table (docs/DATABASE_SETUP.md section 9)


def downgrade() -> None:
    op.drop_index("ix_evidence_observation", table_name="evidence")
    op.drop_index("ix_evidence_issue", table_name="evidence")
    op.drop_index("ix_evidence_asset_created", table_name="evidence")
    op.drop_table("evidence")
