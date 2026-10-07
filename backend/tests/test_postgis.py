"""Runs only against a real PostgreSQL+PostGIS database (TEST_DATABASE_URL).

Safety design (this suite may be pointed at the *development* database):
  * Every test works inside a uniquely named schema `gg_test_<8 hex>`; the name is validated before any DDL,
    and `public`, `extensions` and every other schema are never targeted.
  * Application tables are created unqualified, and the connection `search_path` is `<test schema>, extensions`
    (no `public`), so migrations and downgrades cannot resolve to anything outside the test schema.
  * A canary snapshot of all tables outside the test schema is taken before and compared after teardown; any
    difference fails the run loudly.
PostGIS itself is installed once, in POSTGIS_SCHEMA (idempotent `CREATE EXTENSION IF NOT EXISTS`).
"""

from __future__ import annotations

import re
import secrets

import pytest
from alembic import command
from sqlalchemy import inspect, text

from app.core.config import Settings
from app.core.db import build_engine
from tests.conftest import postgis_url, requires_postgis
from tests.pgsupport import SAFE_NAME, alembic_cfg, snapshot_tables

pytestmark = [pytest.mark.postgis, requires_postgis]


def _settings(schema: str | None = None) -> Settings:
    kw = {"db_schema": schema} if schema else {}
    return Settings(env="test", database_url=postgis_url, jwt_secret="x" * 40, _env_file=None, **kw)


@pytest.fixture
def pg_schema():
    """Yield (engine, schema) for a throwaway schema; always drop it; fail if anything else changed."""
    schema = f"gg_test_{secrets.token_hex(4)}"
    assert SAFE_NAME.match(schema)  # defence in depth: never DROP anything but a generated test schema
    admin = build_engine(_settings())
    before = snapshot_tables(admin, exclude=schema)
    engine = build_engine(_settings(schema))
    try:
        yield engine, schema
    finally:
        engine.dispose()
        assert SAFE_NAME.match(schema)
        with admin.begin() as c:
            c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        after = snapshot_tables(admin, exclude=schema)
        admin.dispose()
        assert after == before, f"tests changed tables outside {schema}: +{after - before} -{before - after}"


def _migrate(schema: str, direction: str = "up"):
    cfg = alembic_cfg(postgis_url)
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


def test_connection_uses_tls_and_isolated_search_path(pg_schema):
    engine, schema = pg_schema
    with engine.connect() as c:
        if Settings(_env_file=None).db_sslmode == "require":
            # client->server leg; pg_stat_ssl would report the pooler->database hop for pooled connections
            assert c.connection.dbapi_connection.pgconn.ssl_in_use is True
        path = c.execute(text("SHOW search_path")).scalar() or ""
        assert path.replace('"', "").replace(" ", "") == f"{schema},extensions"
        assert "public" not in path


def test_postgis_is_in_a_dedicated_schema_not_public(pg_schema):
    engine, schema = pg_schema
    _migrate(schema)
    with engine.connect() as c:
        where = c.execute(
            text(
                "SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace "
                "WHERE e.extname='postgis'"
            )
        ).scalar()
        assert where != "public", "PostGIS must not live in public (exposes spatial_ref_sys via the Data API)"
        assert c.execute(text("SELECT postgis_version()")).scalar().startswith("3.")


def test_migration_creates_schema_and_objects_and_is_reversible(pg_schema):
    engine, schema = pg_schema
    _migrate(schema)  # creates the (not yet existing) schema itself
    insp = inspect(engine)
    assert {"users", "organizations", "workspaces", "memberships", "refresh_tokens", "alembic_version"} <= set(
        insp.get_table_names(schema=schema)
    )
    cols = {c["name"]: c for c in insp.get_columns("workspaces", schema=schema)}
    assert str(cols["settings"]["type"]).upper().startswith("JSONB"), "JSON columns must be JSONB on PostgreSQL"
    _migrate(schema, "down")
    assert set(inspect(engine).get_table_names(schema=schema)) <= {"alembic_version"}


def test_unqualified_geometry_resolves_through_search_path(pg_schema):
    engine, _ = pg_schema
    with engine.connect() as c:
        c.execute(text("CREATE TEMP TABLE _g (id int, p geometry(Point, 4326))"))
        c.execute(text("INSERT INTO _g VALUES (1, ST_SetSRID(ST_MakePoint(72.97, 19.2), 4326))"))
        assert c.execute(text("SELECT id FROM _g WHERE p && ST_MakeEnvelope(72, 19, 73, 20, 4326)")).scalar() == 1
        assert c.execute(text("SELECT id FROM _g WHERE p && ST_MakeEnvelope(0, 0, 1, 1, 4326)")).scalar() is None


def test_postgres_enforces_check_constraints(pg_schema):
    """CHECK constraints are real in PostgreSQL (guards against SQLite-only confidence)."""
    engine, schema = pg_schema
    _migrate(schema)
    with engine.connect() as c:
        c.execute(
            text(
                "INSERT INTO organizations (id, name, slug, created_at, updated_at) "
                "VALUES (gen_random_uuid(), 'o', 'o-slug', now(), now())"
            )
        )
        with pytest.raises(Exception) as bad_mode:
            c.execute(
                text(
                    "INSERT INTO workspaces (id, organization_id, name, mode, timezone, settings, capabilities, "
                    "key_counters, created_at, updated_at) SELECT gen_random_uuid(), id, 'w', 'not_a_mode', 'UTC', "
                    "'{}', '{}', '{}', now(), now() FROM organizations"
                )
            )
        assert "ck_workspaces_mode" in str(bad_mode.value)


# ---------------------------------------------------------------- Row Level Security (ADR-023)


def _app_tables(c, schema: str) -> list[tuple[str, bool]]:
    rows = c.execute(
        text(
            "SELECT c.relname, c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :s AND c.relkind IN ('r','p') ORDER BY 1"
        ),
        {"s": schema},
    ).all()
    return [(r[0], bool(r[1])) for r in rows]


def test_every_application_table_has_rls_enabled_and_no_policies(pg_schema):
    """Guard for future migrations: a new table without `enable_rls(...)` fails here."""
    engine, schema = pg_schema
    _migrate(schema)
    with engine.connect() as c:
        tables = _app_tables(c, schema)
        assert tables, "no tables found"
        missing = [t for t, on in tables if not on]
        assert not missing, f"tables without RLS: {missing} (call app.core.rls.enable_rls in the migration)"
        policies = c.execute(text("SELECT count(*) FROM pg_policies WHERE schemaname = :s"), {"s": schema}).scalar()
        assert policies == 0, "policies are not expected yet; see app/core/rls.py before adding any"


def test_provider_api_roles_have_no_access_to_the_schema(pg_schema):
    engine, schema = pg_schema
    _migrate(schema)
    with engine.connect() as c:
        present = [
            r[0] for r in c.execute(text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated')"))
        ]
        tables = [t for t, _ in _app_tables(c, schema)]
        for role in present:  # empty on a plain PostgreSQL container: nothing to check there
            assert not c.execute(
                text("SELECT has_schema_privilege(:r, :s, 'USAGE')"), {"r": role, "s": schema}
            ).scalar()
            for t in tables:
                for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    ok = c.execute(
                        text("SELECT has_table_privilege(:r, :t, :p)"), {"r": role, "t": f'"{schema}"."{t}"', "p": priv}
                    ).scalar()
                    assert not ok, f"{role} has {priv} on {t}"


def test_backend_role_operates_normally_with_rls_enabled(pg_schema):
    """The runtime role must still read and write: it owns the tables and/or has BYPASSRLS."""
    engine, schema = pg_schema
    _migrate(schema)
    with engine.begin() as c:
        owner, bypass = c.execute(
            text(
                "SELECT (SELECT pg_get_userbyid(relowner) = current_user FROM pg_class WHERE oid = CAST(:t AS regclass)), "
                "(SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user)"
            ),
            {"t": f'"{schema}"."organizations"'},
        ).one()
        assert owner or bypass, "backend role neither owns the tables nor bypasses RLS: it would see no rows"
        c.execute(
            text(
                "INSERT INTO organizations (id, name, slug, created_at, updated_at) VALUES "
                "(gen_random_uuid(), 'o', 'rls-probe', now(), now())"
            )
        )
        assert c.execute(text("SELECT count(*) FROM organizations WHERE slug = 'rls-probe'")).scalar() == 1


def test_rls_really_blocks_a_role_that_neither_owns_nor_bypasses(pg_schema):
    """Prove the barrier works: a throwaway role granted SELECT still sees zero rows (RLS, no policy)."""
    engine, schema = pg_schema
    _migrate(schema)
    role = f"gg_rls_probe_{secrets.token_hex(4)}"
    assert re.match(r"^gg_rls_probe_[0-9a-f]{8}$", role)
    setup = [
        f'CREATE ROLE "{role}" NOLOGIN',
        f'GRANT "{role}" TO CURRENT_USER WITH SET TRUE',
        f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"',
        f'GRANT SELECT ON "{schema}".organizations TO "{role}"',
    ]
    # Role setup and cleanup are committed on their own connection (roles are cluster-wide objects).
    admin = engine.execution_options(isolation_level="AUTOCOMMIT")
    created = False
    try:
        with admin.connect() as c:
            for stmt in setup:
                c.execute(text(stmt))
                created = created or stmt.startswith("CREATE ROLE")
        with engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO organizations (id, name, slug, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), 'o', 'visible-to-owner', now(), now())"
                )
            )
            assert c.execute(text("SELECT count(*) FROM organizations")).scalar() == 1  # owner sees it
            c.execute(text(f'SET LOCAL ROLE "{role}"'))
            assert c.execute(text("SELECT current_user")).scalar() == role
            assert c.execute(text("SELECT count(*) FROM organizations")).scalar() == 0  # RLS hides it
    finally:
        if created:
            with admin.connect() as c:
                c.execute(text(f'DROP OWNED BY "{role}"'))
                c.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
