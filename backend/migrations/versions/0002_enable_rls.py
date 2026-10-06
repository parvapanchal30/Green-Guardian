"""enable row level security on all application tables; lock provider API roles out of the schema

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-07

PostgreSQL only (no-op on other dialects). See app/core/rls.py for the security model.
"""

from app.core import rls

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    rls.enable_rls_everywhere()  # includes alembic_version
    rls.lock_out_api_roles()


def downgrade() -> None:
    # Re-opening access is never automatic: privileges for API roles are NOT restored.
    rls.disable_rls_everywhere()
