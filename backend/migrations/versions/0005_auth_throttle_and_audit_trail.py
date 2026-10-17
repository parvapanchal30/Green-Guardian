"""auth throttle and audit trail

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-17 14:38:35.720495
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core import append_only, rls

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_throttle",
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_auth_throttle")),
    )
    op.create_table(
        "audit_events",
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column(
            "details", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("outcome IN ('success', 'failure', 'denied')", name=op.f("ck_audit_events_outcome")),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_audit_events_actor_id_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_audit_events_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index("ix_audit_events_action_time", "audit_events", ["action", "occurred_at"], unique=False)
    op.create_index("ix_audit_events_actor_time", "audit_events", ["actor_id", "occurred_at"], unique=False)
    op.create_index("ix_audit_events_request", "audit_events", ["request_id"], unique=False)
    op.create_index("ix_audit_events_target", "audit_events", ["target_type", "target_id"], unique=False)
    op.create_index("ix_audit_events_workspace_time", "audit_events", ["workspace_id", "occurred_at"], unique=False)
    # The audit trail can never be rewritten, even by a bug, a script or a hand-typed statement (PostgreSQL trigger;
    # the ORM also refuses). Deny-by-default RLS on both tables, like every application table.
    append_only.install_function()  # idempotent (CREATE OR REPLACE)
    append_only.make_append_only("audit_events")
    rls.enable_rls("audit_events")
    rls.enable_rls("auth_throttle")


def downgrade() -> None:
    # dropping the table drops its trigger; the shared trigger function stays (other tables use it)
    op.drop_index("ix_audit_events_workspace_time", table_name="audit_events")
    op.drop_index("ix_audit_events_target", table_name="audit_events")
    op.drop_index("ix_audit_events_request", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_time", table_name="audit_events")
    op.drop_index("ix_audit_events_action_time", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("auth_throttle")
