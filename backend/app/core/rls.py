"""Row Level Security helpers for Alembic migrations (PostgreSQL only; no-ops elsewhere).

Security model (docs/DATABASE_SETUP.md section 9, ADR-023):
  * Tenancy is enforced by the backend service layer; the database is a second, deny-by-default barrier.
  * Every application table has RLS ENABLED and *no policies*: any role without BYPASSRLS that does not own
    the table sees zero rows and can change none.
  * The backend connects as the table owner (and, on Supabase, `postgres` also has BYPASSRLS), so the app is
    unaffected. We deliberately do NOT use FORCE ROW LEVEL SECURITY.
  * Provider API roles (`anon`, `authenticated`) get no privileges on the application schema at all.
  * If a separate runtime role that neither owns the tables nor has BYPASSRLS is ever introduced, add explicit
    policies in the same migration, otherwise that role will see no rows (intended fail-closed behaviour).

Every new migration that creates a table MUST call `enable_rls("<table>")` (tests enforce this).
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
API_ROLES = ("anon", "authenticated")  # roles a hosted provider may expose through its HTTP API


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def current_schema() -> str:
    schema = op.get_bind().execute(sa.text("SELECT current_schema()")).scalar()
    assert isinstance(schema, str) and _IDENT.match(schema), f"unexpected schema name {schema!r}"
    return schema


def enable_rls(table: str) -> None:
    """ENABLE ROW LEVEL SECURITY on `table` in the current application schema."""
    if not _is_pg():
        return
    assert _IDENT.match(table), table
    op.execute(f'ALTER TABLE "{current_schema()}"."{table}" ENABLE ROW LEVEL SECURITY')


def disable_rls(table: str) -> None:
    if not _is_pg():
        return
    assert _IDENT.match(table), table
    op.execute(f'ALTER TABLE "{current_schema()}"."{table}" DISABLE ROW LEVEL SECURITY')


def enable_rls_everywhere() -> list[str]:
    """ENABLE RLS on every base table currently in the application schema; returns the table names."""
    if not _is_pg():
        return []
    schema = current_schema()
    rows = op.get_bind().execute(
        sa.text("SELECT tablename FROM pg_tables WHERE schemaname = :s ORDER BY tablename"), {"s": schema}
    )
    names = [r[0] for r in rows]
    for t in names:
        enable_rls(t)
    return names


def disable_rls_everywhere() -> None:
    if not _is_pg():
        return
    for t in [
        r[0]
        for r in op.get_bind().execute(
            sa.text("SELECT tablename FROM pg_tables WHERE schemaname = :s"), {"s": current_schema()}
        )
    ]:
        disable_rls(t)


def lock_out_api_roles() -> None:
    """Revoke every privilege on the application schema from provider API roles (when those roles exist) and make
    sure objects created later do not inherit grants for them. Safe to run repeatedly and on providers without
    these roles."""
    if not _is_pg():
        return
    schema = current_schema()
    op.execute(
        f"""
        DO $$
        DECLARE r text;
        BEGIN
          FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
              EXECUTE format('REVOKE ALL ON SCHEMA %I FROM %I', '{schema}', r);
              EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM %I', '{schema}', r);
              EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA %I FROM %I', '{schema}', r);
              EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA %I FROM %I', '{schema}', r);
              EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON TABLES FROM %I', '{schema}', r);
              EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON SEQUENCES FROM %I', '{schema}', r);
              EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON FUNCTIONS FROM %I', '{schema}', r);
            END IF;
          END LOOP;
        END $$;
        """
    )
