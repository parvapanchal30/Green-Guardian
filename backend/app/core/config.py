"""Application settings. Everything comes from environment variables (or a local, gitignored .env)."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

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

    # --- http ---
    cors_origins: list[str] = ["http://localhost:5173"]

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
        if self.env == "production":
            if len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be at least 32 characters in production")
            if self.weather_provider == "mock":
                raise ValueError("WEATHER_PROVIDER=mock is not allowed in production")
            if self.storage_provider == "memory":
                raise ValueError("STORAGE_PROVIDER=memory is not allowed in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
