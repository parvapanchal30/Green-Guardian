"""evaluation-protocol registry (Stage D3)

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-18

Expand-only: two new tables. Both are append-only (trigger on PostgreSQL) with deny-by-default row-level security.
`protocol_signoffs.qualification_verified` is locked to false by a CHECK constraint: the application cannot verify a
qualification, and a future verification feature must remove the lock deliberately.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core import append_only, rls

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "evaluation_protocols",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", JSON, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_evaluation_protocols_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_evaluation_protocols_created_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_protocols")),
        sa.UniqueConstraint("workspace_id", "id", name="uq_evaluation_protocols_workspace_id_id"),
        sa.UniqueConstraint("workspace_id", "key", "version", name="uq_evaluation_protocols_key_version"),
    )
    op.create_table(
        "protocol_signoffs",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("protocol_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("decision", sa.String(8), nullable=False),
        sa.Column("signer_id", sa.Uuid(), nullable=False),
        sa.Column("declared_qualification", sa.String(300)),
        sa.Column("qualification_verified", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "role IN ('plant_pathologist', 'data_owner', 'independent_evaluator')",
            name=op.f("ck_protocol_signoffs_role"),
        ),
        sa.CheckConstraint("decision IN ('approve', 'reject')", name=op.f("ck_protocol_signoffs_decision")),
        sa.CheckConstraint(
            "qualification_verified = false", name=op.f("ck_protocol_signoffs_qualification_unverifiable")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_protocol_signoffs_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["signer_id"], ["users.id"], name=op.f("fk_protocol_signoffs_signer_id_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "protocol_id"],
            ["evaluation_protocols.workspace_id", "evaluation_protocols.id"],
            name="fk_protocol_signoffs_protocol",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_protocol_signoffs")),
    )
    op.create_index("ix_protocol_signoffs_protocol_at", "protocol_signoffs", ["protocol_id", "at"])
    append_only.install_function()
    for t in ("evaluation_protocols", "protocol_signoffs"):
        append_only.make_append_only(t)
        rls.enable_rls(t)


def downgrade() -> None:
    op.drop_table("protocol_signoffs")
    op.drop_table("evaluation_protocols")
