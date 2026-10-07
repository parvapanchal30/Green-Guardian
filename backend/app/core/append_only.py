"""Append-only enforcement for history tables (PostgreSQL only; no-op elsewhere).

A BEFORE UPDATE/DELETE trigger rejects any change to a row, so observations and status histories cannot be
rewritten by a bug, a script or a hand-typed statement (ADR-004). Corrections are new rows.
The trigger function pins `search_path` (hosted-provider linters flag mutable function search paths) and is not
executable by PUBLIC.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
FUNCTION = "gg_forbid_mutation"


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def install_function() -> None:
    if not _is_pg():
        return
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = ''
        AS $$
        BEGIN
          RAISE EXCEPTION 'append-only table %.%: % is not allowed', TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
            USING ERRCODE = 'integrity_constraint_violation';
        END
        $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {FUNCTION}() FROM PUBLIC")


def make_append_only(table: str) -> None:
    if not _is_pg():
        return
    assert _IDENT.match(table), table
    op.execute(
        f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION {FUNCTION}()"
    )


def drop_function() -> None:
    if _is_pg():
        op.execute(f"DROP FUNCTION IF EXISTS {FUNCTION}()")


def _unused() -> None:  # keep `sa` import for type checkers that inspect helper modules
    _ = sa
