"""Runs only against a real PostgreSQL+PostGIS database (TEST_DATABASE_URL). Destructive by design:
it migrates up and back down on that database, so point it at a disposable test database only."""

from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import text

from app.core.config import Settings
from app.core.db import build_engine
from tests.conftest import postgis_url, requires_postgis
from tests.test_migrations import _cfg

pytestmark = [pytest.mark.postgis, requires_postgis]


@pytest.fixture
def pg_engine():
    s = Settings(env="test", database_url=postgis_url, jwt_secret="x" * 40, _env_file=None)
    engine = build_engine(s)
    yield engine
    engine.dispose()


def test_server_meets_requirements(pg_engine):
    with pg_engine.connect() as c:
        major = int(c.execute(text("SHOW server_version_num")).scalar()) // 10000
        assert major >= 15, f"PostgreSQL {major} < 15"
        assert c.execute(text("SELECT 1 FROM pg_available_extensions WHERE name='postgis'")).first(), (
            "PostGIS not available"
        )


def test_migrations_install_postgis_and_search_path_resolves_geometry(pg_engine):
    cfg = _cfg(postgis_url)
    command.upgrade(cfg, "head")
    try:
        with pg_engine.connect() as c:
            assert c.execute(text("SELECT postgis_version()")).scalar().startswith("3.")
            sp = c.execute(text("SHOW search_path")).scalar()
            assert "extensions" in sp or "public" in sp
            # unqualified geometry type + ST_* functions resolve through the connection search_path
            c.execute(text("CREATE TEMP TABLE _g (id int, p geometry(Point, 4326))"))
            c.execute(text("INSERT INTO _g VALUES (1, ST_SetSRID(ST_MakePoint(72.97, 19.2), 4326))"))
            hit = c.execute(text("SELECT id FROM _g WHERE p && ST_MakeEnvelope(72, 19, 73, 20, 4326)")).scalar()
            assert hit == 1
    finally:
        command.downgrade(cfg, "base")
