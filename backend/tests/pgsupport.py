"""Shared helpers for tests that use the real PostgreSQL+PostGIS database (never imported by production code)."""

from __future__ import annotations

import re
from pathlib import Path

from alembic.config import Config
from sqlalchemy import text

BACKEND = Path(__file__).resolve().parents[1]
SAFE_NAME = re.compile(r"^gg_test_[0-9a-f]{8}$")


def alembic_cfg(url: str, schema: str | None = None) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    if schema:
        cfg.set_main_option("db_schema", schema)
    return cfg


def snapshot_tables(engine, exclude: str) -> set[tuple[str, str]]:
    """(schema, table) for every base table outside the test schema: the canary compared before and after a run."""
    with engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_schema <> 'information_schema' AND table_schema NOT LIKE 'pg\\_%' "
                "AND table_schema <> :ex AND table_type = 'BASE TABLE'"
            ),
            {"ex": exclude},
        ).all()
    return {(r[0], r[1]) for r in rows}


def drop_test_schema(admin_engine, schema: str) -> None:
    assert SAFE_NAME.match(schema), f"refusing to drop {schema!r}: not a generated test schema"
    with admin_engine.begin() as c:
        c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
