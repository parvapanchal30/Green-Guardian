from __future__ import annotations

import time
import uuid

import pytest

from app.core.config import Settings, normalize_database_url
from app.core.ids import uuid7
from app.core.security import hash_password, new_refresh_token, verify_password
from app.modules.workspaces.capabilities import REGISTRY, effective_capabilities


@pytest.fixture(autouse=True)
def _ambient_configuration_does_not_leak_into_settings_tests(monkeypatch):
    """`Settings` reads the process environment. CI runs with DB_SSLMODE=disable (its throwaway database container has no
    TLS) and developers have their own values; these tests are about defaults and guards, so start from a clean slate."""
    for name in ("DB_SSLMODE", "DATABASE_URL", "CORS_ORIGINS", "ENV", "STORAGE_PROVIDER", "WEATHER_PROVIDER"):
        monkeypatch.delenv(name, raising=False)


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
    with pytest.raises(ValueError, match="POSTGIS_SCHEMA"):
        Settings(postgis_schema="extensions; DROP TABLE users", jwt_secret="x" * 40, **base)
    assert (
        Settings(
            env="production", jwt_secret="x" * 40, cors_origins=["https://app.example.org"], **base
        ).weather_provider
        == "open_meteo"
    )


def test_a_signing_secret_is_required_outside_tests(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    for env in ("development", "production"):
        with pytest.raises(ValueError, match="JWT_SECRET must be at least 32"):
            Settings(env=env, jwt_secret="", _env_file=None)
        with pytest.raises(ValueError, match="JWT_SECRET must be at least 32"):
            Settings(env=env, jwt_secret="too-short", _env_file=None)
    assert Settings(env="development", jwt_secret="x" * 32, _env_file=None).env == "development"
    assert Settings(env="test", jwt_secret="", _env_file=None).env == "test"  # the test harness may use any key"


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
    base = dict(_env_file=None, jwt_secret="x" * 40)
    with pytest.raises(ValueError, match="brackets"):
        Settings(database_url="postgresql://postgres:[my-secret]@db.example.supabase.co:5432/postgres", **base)
    # a password that merely contains brackets in the middle is left alone (URL-encode it if it has specials)
    ok = Settings(database_url="postgresql://postgres:ab%5Bcd@db.example.co:5432/postgres", **base)
    assert ok.database_url.startswith("postgresql+psycopg://")


def test_db_schema_must_be_a_simple_identifier():
    with pytest.raises(ValueError):
        Settings(db_schema='x"; DROP SCHEMA public; --', jwt_secret="x" * 40, _env_file=None)


def test_app_schema_defaults_to_a_dedicated_schema_not_public():
    s = Settings(jwt_secret="x" * 40, _env_file=None)
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
    # Hermetic: CI exports DB_SSLMODE=disable for its TLS-less container; this test is about the defaults.
    for var in (
        "DB_SSLMODE",
        "DB_CONNECT_TIMEOUT_S",
        "DB_POOL_PRE_PING",
        "DB_SCHEMA",
        "POSTGIS_SCHEMA",
        "DB_POOL_MODE",
    ):
        monkeypatch.delenv(var, raising=False)
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


# ------------------------------------------------------------------------------------------------ production hosting guards
PROD = dict(env="production", jwt_secret="x" * 40, _env_file=None)


@pytest.mark.parametrize(
    ("origin", "fragment"),
    [
        ("*", "wildcards"),
        ("https://*.example.org", "wildcards"),
        ("http://app.example.org", "https origin"),
        ("app.example.org", "https origin"),
        ("https://localhost", "local address"),
        ("https://127.0.0.1:8443", "local address"),
        ("https://app.example.org/", "bare origin"),
        ("https://app.example.org/path", "bare origin"),
        ("https://user:pw@app.example.org", "bare origin"),
    ],
)
def test_production_refuses_unsafe_cors_origins(origin, fragment):
    with pytest.raises(ValueError, match=fragment):
        Settings(cors_origins=[origin], **PROD)


def test_production_accepts_exact_https_origins_and_the_default_localhost_origin_is_refused():
    ok = Settings(cors_origins=["https://app.example.org", "https://staging.example.org:8443"], **PROD)
    assert ok.cors_origins == ["https://app.example.org", "https://staging.example.org:8443"]
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(**PROD)  # the development default (http://localhost:5173) must be replaced explicitly


def test_development_keeps_its_localhost_default():
    assert Settings(env="development", jwt_secret="x" * 40, _env_file=None).cors_origins == ["http://localhost:5173"]


@pytest.mark.parametrize("mode", ["disable", "allow", "prefer"])
def test_production_requires_tls_to_the_database_via_the_url(mode):
    with pytest.raises(ValueError, match="must use TLS"):
        Settings(cors_origins=["https://app.example.org"], database_url=f"postgresql://u:p@h/db?sslmode={mode}", **PROD)


@pytest.mark.parametrize("mode", ["disable", "prefer"])
def test_production_requires_tls_to_the_database_via_the_setting(mode):
    with pytest.raises(ValueError, match="must use TLS"):
        Settings(cors_origins=["https://app.example.org"], db_sslmode=mode, **PROD)


def test_a_tls_setting_in_the_url_overrides_a_weaker_default_and_vice_versa():
    origins = ["https://app.example.org"]
    assert Settings(
        cors_origins=origins, db_sslmode="disable", database_url="postgresql://u:p@h/db?sslmode=require", **PROD
    )
    assert Settings(cors_origins=origins, db_sslmode="verify-full", **PROD).db_sslmode == "verify-full"
    with pytest.raises(ValueError, match="must use TLS"):
        Settings(
            cors_origins=origins, db_sslmode="require", database_url="postgresql://u:p@h/db?sslmode=disable", **PROD
        )


def test_cors_answers_only_the_configured_origin_and_never_allows_credentials(client):
    allowed = client.options(
        "/api/v1/me",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-credentials" not in allowed.headers  # tokens travel in a header, never in cookies
    for origin in ("https://evil.example", "http://localhost:5174", "null"):
        refused = client.options("/api/v1/me", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
        assert "access-control-allow-origin" not in refused.headers, origin
    assert "x-request-id" in {
        k.lower() for k in client.get("/healthz", headers={"Origin": "http://localhost:5173"}).headers
    }
