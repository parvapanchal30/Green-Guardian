from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("ENV", "test")

from app.core.config import Settings, get_settings, normalize_database_url  # noqa: E402
from app.core.db import build_engine, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402
from app.modules.weather.mock import MockWeatherProvider  # noqa: E402
from app.modules.weather.service import WeatherService, get_weather_service  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="x" * 40,
        weather_provider="mock",
        _env_file=None,
    )


@pytest.fixture
def app(settings):
    engine = build_engine(settings)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    def _db():
        db = maker()
        try:
            yield db
        finally:
            db.close()

    application = create_app(settings)
    application.dependency_overrides[get_db] = _db
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_weather_service] = lambda: WeatherService(MockWeatherProvider(), 60)
    application.state.session_maker = maker
    yield application
    engine.dispose()


@pytest.fixture
def client(app):
    return TestClient(app)


class Actor:
    """A registered, logged-in user with a ready Authorization header."""

    def __init__(self, client: TestClient, email: str, name: str):
        self.client, self.email, self.name = client, email, name
        r = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "name": name})
        assert r.status_code == 201, r.text
        self.id = r.json()["id"]
        r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        self.tokens = r.json()
        self.headers = {"Authorization": f"Bearer {self.tokens['access_token']}"}

    def get(self, url, **kw):
        return self.client.get(url, headers=self.headers, **kw)

    def post(self, url, json=None, **kw):
        return self.client.post(url, json=json, headers=self.headers, **kw)

    def patch(self, url, json=None, **kw):
        return self.client.patch(url, json=json, headers=self.headers, **kw)

    def delete(self, url, **kw):
        return self.client.delete(url, headers=self.headers, **kw)

    def create_workspace(self, name="City Green Cover", mode="green_management") -> str:
        r = self.post("/api/v1/workspaces", {"name": name, "mode": mode})
        assert r.status_code == 201, r.text
        return r.json()["id"]


@pytest.fixture
def make_actor(client):
    def _make(email: str, name: str = "Test User") -> Actor:
        return Actor(client, email, name)

    return _make


def _load_test_database_url(env_file=None) -> str:
    """TEST_DATABASE_URL from the process environment, else from backend/.env.

    (`Settings` reads .env itself, but os.getenv does not, so without this the value would be silently ignored.)
    """
    if value := os.getenv("TEST_DATABASE_URL"):
        return value
    from pathlib import Path

    from dotenv import dotenv_values

    path = env_file or Path(__file__).resolve().parents[1] / ".env"
    value = dotenv_values(path).get("TEST_DATABASE_URL") or ""
    return normalize_database_url(value) if value else ""


postgis_url = _load_test_database_url()

if os.getenv("GG_REQUIRE_POSTGRES_TESTS") == "1" and not postgis_url:
    # Set in CI: a missing database must fail the run, never turn into skipped tests.
    raise RuntimeError("GG_REQUIRE_POSTGRES_TESTS=1 but TEST_DATABASE_URL is not set")
requires_postgis = pytest.mark.skipif(
    not postgis_url, reason="TEST_DATABASE_URL not set: PostgreSQL+PostGIS behaviour is NOT verified in this run"
)
