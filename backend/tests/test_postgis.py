"""Runs only against a real PostgreSQL+PostGIS database (TEST_DATABASE_URL).

Isolation: every test works inside a uniquely named throwaway schema that is dropped afterwards, so this
suite never touches tables in `public` (it is safe even if TEST_DATABASE_URL equals the dev database).
PostGIS itself is installed once, in POSTGIS_SCHEMA (idempotent).
"""

from __future__ import annotations

import secrets

import pytest
from alembic import command
from sqlalchemy import inspect, text

from app.core.config import Settings
from app.core.db import build_engine
from tests.conftest import postgis_url, requires_postgis
from tests.test_migrations import _cfg

pytestmark = [pytest.mark.postgis, requires_postgis]


@pytest.fixture
def pg_schema():
    """Create a throwaway schema, yield (engine, schema), always drop it."""
    schema = f"gg_test_{secrets.token_hex(4)}"
    admin = build_engine(Settings(env="test", database_url=postgis_url, jwt_secret="x" * 40, _env_file=None))
    with admin.begin() as c:
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = build_engine(
        Settings(env="test", database_url=postgis_url, jwt_secret="x" * 40, db_schema=schema, _env_file=None)
    )
    try:
        yield engine, schema
    finally:
        engine.dispose()
        with admin.begin() as c:
            c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def _migrate(schema: str, direction: str = "up"):
    cfg = _cfg(postgis_url)
    cfg.set_main_option("db_schema", schema)
    return command.upgrade(cfg, "head") if direction == "up" else command.downgrade(cfg, "base")


def test_server_meets_requirements(pg_schema):
    engine, _ = pg_schema
    with engine.connect() as c:
        major = int(c.execute(text("SHOW server_version_num")).scalar() or 0) // 10000
        assert major >= 15, f"PostgreSQL {major} < 15"
        assert c.execute(text("SELECT 1 FROM pg_available_extensions WHERE name='postgis'")).first(), (
            "PostGIS not available"
        )


def test_postgis_is_in_a_dedicated_schema_not_public(pg_schema):
    engine, _ = pg_schema
    _migrate(pg_schema[1])
    with engine.connect() as c:
        where = c.execute(
            text(
                "SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname='postgis'"
            )
        ).scalar()
        assert where != "public", "PostGIS must not live in public (exposes spatial_ref_sys)"
        assert c.execute(text("SELECT postgis_version()")).scalar().startswith("3.")


def test_migration_creates_schema_objects_and_is_reversible(pg_schema):
    engine, schema = pg_schema
    _migrate(schema)
    insp = inspect(engine)
    tables = set(insp.get_table_names(schema=schema))
    assert {"users", "organizations", "workspaces", "memberships", "refresh_tokens", "alembic_version"} <= tables
    cols = {c["name"]: c for c in insp.get_columns("workspaces", schema=schema)}
    assert str(cols["settings"]["type"]).upper().startswith("JSONB"), "JSON columns must be JSONB on PostgreSQL"
    _migrate(schema, "down")
    assert set(inspect(engine).get_table_names(schema=schema)) <= {"alembic_version"}


def test_unqualified_geometry_resolves_through_search_path(pg_schema):
    engine, _ = pg_schema
    with engine.connect() as c:
        c.execute(text("CREATE TEMP TABLE _g (id int, p geometry(Point, 4326))"))
        c.execute(text("INSERT INTO _g VALUES (1, ST_SetSRID(ST_MakePoint(72.97, 19.2), 4326))"))
        hit = c.execute(text("SELECT id FROM _g WHERE p && ST_MakeEnvelope(72, 19, 73, 20, 4326)")).scalar()
        assert hit == 1
        miss = c.execute(text("SELECT id FROM _g WHERE p && ST_MakeEnvelope(0, 0, 1, 1, 4326)")).scalar()
        assert miss is None


def test_postgres_enforces_constraints_sqlite_does_not(pg_schema):
    """CHECK constraints from the models are real in PostgreSQL (guards against SQLite-only confidence)."""
    engine, schema = pg_schema
    _migrate(schema)
    with engine.connect() as c:
        with pytest.raises(Exception) as bad_mode:
            c.execute(
                text(
                    "INSERT INTO organizations (id, name, slug, created_at, updated_at) VALUES "
                    "(gen_random_uuid(), 'o', 'o-slug', now(), now())"
                )
            )
            c.execute(
                text(
                    "INSERT INTO workspaces (id, organization_id, name, mode, timezone, settings, capabilities, key_counters, "
                    "created_at, updated_at) SELECT gen_random_uuid(), id, 'w', 'not_a_mode', 'UTC', '{}', '{}', '{}', now(), now() "
                    "FROM organizations"
                )
            )
        assert "ck_workspaces_mode" in str(bad_mode.value)
