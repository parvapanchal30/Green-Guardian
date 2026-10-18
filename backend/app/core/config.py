"""Application settings. Everything comes from environment variables (or a local, gitignored .env)."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qs, urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def normalize_database_url(url: str) -> str:
    """Accept provider-style URLs (postgres:// or postgresql://) and pin the psycopg 3 driver."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _cors_origin_problem(origin: str) -> str | None:
    """Production allows only exact https origins: no wildcard, no localhost, no path (a browser's Origin header has
    none, so an entry with a path or trailing slash would silently never match)."""
    if "*" in origin:
        return "wildcards are not allowed in production; list each origin exactly"
    u = urlparse(origin)
    if u.scheme != "https" or not u.hostname:
        return "must be an https origin such as https://app.example.org"
    if u.hostname == "localhost" or u.hostname.startswith("127.") or u.hostname in ("0.0.0.0", "::1"):
        return "a local address is not a production origin"
    if u.path or u.params or u.query or u.fragment or u.username or u.password:
        return "must be a bare origin (scheme, host and optional port; no path, trailing slash or credentials)"
    return None


def _effective_sslmode(database_url: str, default: str) -> str:
    """The sslmode that will actually be used: an explicit ?sslmode= in the URL wins over DB_SSLMODE."""
    try:
        return parse_qs(urlparse(database_url).query).get("sslmode", [default])[0]
    except ValueError:
        return default


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    # --- database (hosted PostgreSQL + PostGIS; see docs/DATABASE_SETUP.md) ---
    database_url: str = ""
    db_pool_mode: Literal["session", "transaction"] = "session"
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_connect_timeout_s: int = 10
    # A liveness ping on every connection checkout. Safe default; it costs one round trip per request (measured at
    # ~166 ms against a remote hosted database). Disable only when the API runs next to the database and the pooler
    # is stable, and keep pool recycling in mind (see docs/DATABASE_SETUP.md section 10).
    db_pool_pre_ping: bool = True
    postgis_schema: str = "extensions"
    # Schema that holds the application tables (first entry of search_path). NOT `public`: on Supabase `public`
    # is exposed through the Data API with default grants to `anon` (ADR-022). Tests override this per run.
    db_schema: str = "greenguardian"
    # Applied only when the URL has no explicit ?sslmode=. Use "disable"/"prefer" for a local container without TLS.
    db_sslmode: Literal["require", "verify-full", "prefer", "disable"] = "require"

    # --- auth ---
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    # Brute-force protection (identity/throttle.py). Failures are counted per window; reaching a limit locks that key
    # for `auth_lockout_s`, after which counters start fresh. Pair = this email from this address; account = this
    # email from anywhere (deliberately higher, so one attacker cannot lock a victim out); ip = any email from this
    # address.
    auth_failure_window_s: int = 900
    auth_lockout_s: int = 900
    auth_login_max_failures_pair: int = 5
    auth_login_max_failures_account: int = 15
    auth_login_max_failures_ip: int = 30
    auth_refresh_max_failures_ip: int = 30
    auth_register_max_per_ip: int = 10  # attempts per `auth_register_window_s`
    auth_register_window_s: int = 3600

    # Audit retention (modules/audit/retention.py). Records older than this many days may be purged by the housekeeping
    # job; 0 keeps them forever. The database refuses to delete anything younger than 30 days whatever this says.
    audit_retention_days: int = 730
    # Identical access-denied events (same actor, route and reason) are recorded at most once per this many seconds.
    audit_denied_dedupe_s: int = 60

    # --- background worker (python -m app.worker; app/modules/intelligence/scheduler.py) ---
    worker_poll_interval_s: int = 60  # how often the worker looks for workspaces whose agent run is due
    agent_stale_run_s: int = 1800  # a run still "running" after this long is presumed abandoned (crashed worker)
    housekeeping_interval_s: int = 86_400  # audit retention and idle throttle counters

    # --- http ---
    cors_origins: list[str] = ["http://localhost:5173"]
    # Reverse proxies in front of the API. 0 = use the socket peer address; N = trust the Nth entry from the right of
    # X-Forwarded-For. Leave at 0 unless a proxy you control sets that header (otherwise clients can spoof it).
    trusted_proxy_count: int = 0

    # --- weather (behind an abstraction; see app/modules/weather) ---
    # Key of a registered provider (app/modules/weather/registry.py); validated at application startup.
    weather_provider: str = "open_meteo"
    open_meteo_base_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_timeout_s: float = 8.0
    weather_cache_ttl_s: int = 900

    # --- evidence / object storage (behind an abstraction; see app/modules/evidence/storage.py) ---
    # Key of a registered store: "local" (disk, development and single-node), "memory" (tests only).
    storage_provider: str = "local"
    storage_local_dir: str = "var/storage"
    storage_max_bytes: int = 10 * 1024 * 1024
    # Decoded-size guard against decompression bombs (width x height).
    storage_max_pixels: int = 40_000_000

    @field_validator("database_url")
    @classmethod
    def _norm_url(cls, v: str) -> str:
        v = normalize_database_url(v.strip())
        # Providers show `postgresql://user:[YOUR-PASSWORD]@host/...`; the brackets are a placeholder marker.
        if re.search(r"://[^:/@]+:\[[^@]*\]@", v):
            raise ValueError(
                "DATABASE_URL password is wrapped in [brackets]: remove them (they are only a placeholder "
                "marker in provider dashboards). Passwords with special characters must be URL-encoded."
            )
        return v

    @field_validator("audit_retention_days")
    @classmethod
    def _retention(cls, v: int) -> int:
        if v != 0 and v < 30:
            raise ValueError("AUDIT_RETENTION_DAYS must be 0 (keep forever) or at least 30")
        return v

    @field_validator("db_schema")
    @classmethod
    def _db_schema_ident(cls, v: str) -> str:
        if not _IDENT.match(v):
            raise ValueError("DB_SCHEMA must be a simple lowercase identifier")
        return v

    @field_validator("postgis_schema")
    @classmethod
    def _schema_ident(cls, v: str) -> str:
        if not _IDENT.match(v):
            raise ValueError("POSTGIS_SCHEMA must be a simple lowercase identifier")
        return v

    @model_validator(mode="after")
    def _prod_guards(self) -> Settings:
        # A signing key is required wherever real data may be reachable (development talks to a hosted database too).
        if self.env != "test" and len(self.jwt_secret) < 32:
            raise ValueError(
                "JWT_SECRET must be at least 32 characters. Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        if self.env == "production":
            if self.weather_provider == "mock":
                raise ValueError("WEATHER_PROVIDER=mock is not allowed in production")
            if self.storage_provider == "memory":
                raise ValueError("STORAGE_PROVIDER=memory is not allowed in production")
            for origin in self.cors_origins:
                problem = _cors_origin_problem(origin)
                if problem:
                    raise ValueError(f"CORS_ORIGINS entry {origin!r}: {problem}")
            if _effective_sslmode(self.database_url, self.db_sslmode) in ("disable", "allow", "prefer"):
                raise ValueError(
                    "the database connection must use TLS in production: set DB_SSLMODE=require (or verify-full), "
                    "or put sslmode=require in DATABASE_URL"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
