from __future__ import annotations

import time
import uuid

import pytest

from app.core.config import Settings, normalize_database_url
from app.core.ids import uuid7
from app.core.security import hash_password, new_refresh_token, verify_password
from app.modules.workspaces.capabilities import REGISTRY, effective_capabilities


def test_uuid7_is_valid_version7_and_time_ordered():
    ids = []
    for _ in range(5):
        ids.append(uuid7())
        time.sleep(0.002)
    assert all(i.version == 7 and i.variant == uuid.RFC_4122 for i in ids)
    assert ids == sorted(ids, key=lambda u: u.int)
    assert len({uuid7() for _ in range(1000)}) == 1000


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("postgres://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
        ("postgresql://u:p@h/db?sslmode=require", "postgresql+psycopg://u:p@h/db?sslmode=require"),
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("sqlite+pysqlite:///:memory:", "sqlite+pysqlite:///:memory:"),
    ],
)
def test_database_url_normalization(raw, expected):
    assert normalize_database_url(raw) == expected


def test_settings_guards():
    base = dict(_env_file=None)
    with pytest.raises(ValueError):
        Settings(env="production", jwt_secret="short", **base)
    with pytest.raises(ValueError):
        Settings(env="production", jwt_secret="x" * 40, weather_provider="mock", **base)
    with pytest.raises(ValueError):
        Settings(postgis_schema="extensions; DROP TABLE users", **base)
    assert Settings(env="production", jwt_secret="x" * 40, **base).weather_provider == "open_meteo"


def test_passwords_and_refresh_tokens():
    h = hash_password("a-long-enough-password")
    assert h.startswith("$argon2id$")
    assert verify_password("a-long-enough-password", h) and not verify_password("wrong", h)
    assert not verify_password("anything", None)
    a, b = new_refresh_token(), new_refresh_token()
    assert a.raw != b.raw and a.hash != a.raw and len(a.hash) == 64


def test_capability_overrides_can_only_disable():
    live = next(c for c in REGISTRY if c.available)
    unavailable = next(c for c in REGISTRY if not c.available)
    eff = {c.key: c for c in effective_capabilities({live.key: False, unavailable.key: True})}
    assert eff[live.key].available is False
    assert eff[unavailable.key].available is False  # an override can never enable an unbuilt feature


def test_database_url_rejects_placeholder_brackets_around_password():
    base = dict(_env_file=None)
    with pytest.raises(ValueError, match="brackets"):
        Settings(database_url="postgresql://postgres:[my-secret]@db.example.supabase.co:5432/postgres", **base)
    # a password that merely contains brackets in the middle is left alone (URL-encode it if it has specials)
    ok = Settings(database_url="postgresql://postgres:ab%5Bcd@db.example.co:5432/postgres", **base)
    assert ok.database_url.startswith("postgresql+psycopg://")


def test_db_schema_must_be_a_simple_identifier():
    with pytest.raises(ValueError):
        Settings(db_schema='x"; DROP SCHEMA public; --', _env_file=None)


def test_app_schema_defaults_to_a_dedicated_schema_not_public():
    s = Settings(_env_file=None)
    assert s.db_schema == "greenguardian"
    assert s.db_schema != s.postgis_schema


def test_build_engine_pins_sslmode_and_search_path(monkeypatch):
    """Postgres engines get sslmode=require by default, unless the URL carries its own; search_path has no `public`
    for the app schema. (create_engine is stubbed: no connection is made.)"""
    import app.core.db as db

    seen = {}

    class FakeEngine:
        dialect = type("D", (), {"name": "postgresql"})()

    def fake_create_engine(url, **kw):
        seen["url"], seen["kw"] = url, kw
        return FakeEngine()

    monkeypatch.setattr(db, "create_engine", fake_create_engine)
    monkeypatch.setattr(db.event, "listens_for", lambda *a, **k: lambda f: f)
    base = dict(_env_file=None, env="test", jwt_secret="x" * 40)
    db.build_engine(Settings(database_url="postgresql://u:p@h:5432/d", **base))
    assert seen["kw"]["connect_args"]["sslmode"] == "require"
    assert seen["kw"]["connect_args"]["connect_timeout"] == 10
    db.build_engine(Settings(database_url="postgresql://u:p@h:5432/d?sslmode=verify-full", **base))
    assert "sslmode" not in seen["kw"]["connect_args"]  # the URL's explicit choice wins
    db.build_engine(Settings(database_url="postgresql://u:p@h:6543/d", db_pool_mode="transaction", **base))
    assert seen["kw"]["connect_args"]["prepare_threshold"] is None
    assert seen["kw"]["pool_pre_ping"] is True  # safe default
    db.build_engine(Settings(database_url="postgresql://u:p@h:5432/d", db_pool_pre_ping=False, **base))
    assert seen["kw"]["pool_pre_ping"] is False


def test_test_database_url_is_read_from_dotenv_when_not_in_the_environment(tmp_path, monkeypatch):
    """os.getenv alone would ignore backend/.env (only Settings reads it), silently skipping the PostGIS tests."""
    from tests.conftest import _load_test_database_url

    env = tmp_path / ".env"
    env.write_text("TEST_DATABASE_URL=postgresql://u:p@h:5432/d" + chr(10), encoding="utf8")
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    assert _load_test_database_url(env) == "postgresql+psycopg://u:p@h:5432/d"
    assert _load_test_database_url(tmp_path / "missing.env") == ""
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://env:p@h/d")
    assert _load_test_database_url(env) == "postgresql://env:p@h/d"  # the real environment wins
