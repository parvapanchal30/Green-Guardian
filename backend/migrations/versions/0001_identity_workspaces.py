"""identity, organizations, workspaces, memberships, refresh tokens; PostGIS extension

Revision ID: 0001
Revises:
Create Date: 2026-10-06
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(JSONB(), "postgresql")
TZ = sa.DateTime(timezone=True)


def _ensure_postgis(bind) -> None:
    """Idempotently install PostGIS into a dedicated schema (docs/DATABASE_SETUP.md).

    GG_REQUIRE_POSTGIS=false lets this run on a database without PostGIS (tests of non-spatial code only).
    Portable: plain SQL, no provider-specific objects.
    """
    if bind.dialect.name != "postgresql":
        return
    from app.core.config import get_settings

    schema = get_settings().postgis_schema
    require = os.getenv("GG_REQUIRE_POSTGIS", "true").lower() != "false"
    available = bind.execute(sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'postgis'")).first()
    if available:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        op.execute(f'CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA "{schema}"')
    elif require:
        raise RuntimeError(
            "PostGIS is not available on this database. Enable it (see docs/DATABASE_SETUP.md) "
            "or set GG_REQUIRE_POSTGIS=false for non-spatial test databases."
        )


def upgrade() -> None:
    _ensure_postgis(op.get_bind())

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(40)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", TZ),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("settings", JSON, nullable=False),
        sa.Column("capabilities", JSON, nullable=False),
        sa.Column("key_counters", JSON, nullable=False),
        sa.Column("archived_at", TZ),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_workspaces"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_workspaces_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("mode IN ('green_management', 'agricultural_production')", name="ck_workspaces_mode"),
    )
    op.create_index("ix_workspaces_organization_id", "workspaces", ["organization_id"])
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_memberships"),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], name="fk_memberships_workspace_id_workspaces", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_memberships_user_id_users", ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "workspace_id", name="uq_memberships_user_workspace"),
        sa.CheckConstraint("role IN ('owner', 'admin', 'manager', 'worker', 'viewer')", name="ck_memberships_role"),
    )
    op.create_index("ix_memberships_workspace_id", "memberships", ["workspace_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("revoked_at", TZ),
        sa.Column("created_at", TZ, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_refresh_tokens_user_id_users", ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])


def downgrade() -> None:
    # PostGIS is intentionally left installed (other schemas may depend on it).
    op.drop_table("refresh_tokens")
    op.drop_table("memberships")
    op.drop_table("workspaces")
    op.drop_table("organizations")
    op.drop_table("users")
