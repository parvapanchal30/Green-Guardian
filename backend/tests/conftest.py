from __future__ import annotations

import os
import secrets
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("ENV", "test")

from alembic import command  # noqa: E402

from app.core.config import Settings, get_settings, normalize_database_url  # noqa: E402
from app.core.db import build_engine, get_db  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402
from app.modules.evidence.storage import MemoryObjectStore, get_object_store  # noqa: E402
from app.modules.identity.models import Organization, User  # noqa: E402
from app.modules.weather.mock import MockWeatherProvider  # noqa: E402
from app.modules.weather.service import WeatherService, get_weather_service  # noqa: E402
from app.modules.workspaces.models import Membership, Role, Workspace  # noqa: E402
from tests.pgsupport import SAFE_NAME, alembic_cfg, drop_test_schema, snapshot_tables  # noqa: E402

PASSWORD = "correct-horse-battery"
JWT_SECRET = "x" * 40


def _load_test_database_url(env_file=None) -> str:
    """TEST_DATABASE_URL from the process environment, else from backend/.env.

    (`Settings` reads .env itself, but os.getenv does not, so without this the value would be silently ignored.)
    """
    if value := os.getenv("TEST_DATABASE_URL"):
        return value
    from dotenv import dotenv_values

    path = env_file or Path(__file__).resolve().parents[1] / ".env"
    value = dotenv_values(path).get("TEST_DATABASE_URL") or ""
    return normalize_database_url(value) if value else ""


postgis_url = _load_test_database_url()

if os.getenv("GG_REQUIRE_POSTGRES_TESTS") == "1" and not postgis_url:
    # Set in CI: a missing database must fail the run, never turn into skipped tests.
    raise RuntimeError("GG_REQUIRE_POSTGRES_TESTS=1 but TEST_DATABASE_URL is not set")

_requested = os.getenv("GG_TEST_DB", "").lower()  # "", "postgres" or "sqlite"
if _requested == "postgres" and not postgis_url:
    raise RuntimeError("GG_TEST_DB=postgres but TEST_DATABASE_URL is not set")
# PostgreSQL whenever it is available; SQLite is an explicit, clearly reported fast mode for non-spatial iteration.
PG_MODE = bool(postgis_url) and _requested != "sqlite"

requires_postgis = pytest.mark.skipif(
    not postgis_url, reason="TEST_DATABASE_URL not set: PostgreSQL+PostGIS behaviour is NOT verified in this run"
)
requires_pg_mode = pytest.mark.skipif(
    not PG_MODE, reason="needs PostgreSQL mode (TEST_DATABASE_URL set and GG_TEST_DB != sqlite)"
)


def pytest_report_header(config):
    if PG_MODE:
        return "database: PostgreSQL+PostGIS (isolated throwaway schema per session, savepoint rollback per test)"
    return "database: SQLite FAST MODE - PostgreSQL behaviour is NOT verified in this run (set TEST_DATABASE_URL)"


# --------------------------------------------------------------------------------------------------- team seeding


@dataclass
class Member:
    id: uuid.UUID
    email: str
    role: str | None


@dataclass
class Team:
    """Pre-created users/workspaces, committed once (PostgreSQL: per session) so tests do not pay for registration."""

    ws: str  # green_management workspace
    agri_ws: str  # agricultural_production workspace (owner is also a member)
    other_ws: str  # a different tenant
    owner: Member
    manager: Member
    worker: Member
    viewer: Member
    outsider: Member  # a user with no membership anywhere
    other_owner: Member
    settings: Settings = field(repr=False, default=None)  # type: ignore[assignment]

    def headers(self, member: Member) -> dict[str, str]:
        token, _ = create_access_token(member.id, self.settings)  # minted fresh: sessions can outlive a 15 min token
        return {"Authorization": f"Bearer {token}"}


def seed_team(engine, settings: Settings) -> Team:
    tag = secrets.token_hex(3)
    with Session(engine) as s:

        def user(role: str) -> User:
            u = User(email=f"{role}-{tag}@example.com", password_hash="!", name=role.title(), is_active=True)
            s.add(u)
            return u

        users = {r: user(r) for r in ("owner", "manager", "worker", "viewer", "outsider", "other_owner")}

        def workspace(name: str, mode: str, members: dict[str, Role]) -> Workspace:
            org = Organization(name=name, slug=f"{name.lower().replace(' ', '-')}-{tag}")
            s.add(org)
            s.flush()
            ws = Workspace(
                organization_id=org.id,
                name=name,
                mode=mode,
                timezone="UTC",
                settings={},
                capabilities={},
                key_counters={"issue": 0, "task": 0},
            )
            s.add(ws)
            s.flush()
            for key, role in members.items():
                s.add(Membership(workspace_id=ws.id, user_id=users[key].id, role=role.value))
            return ws

        s.flush()
        green = workspace(
            "Team Green",
            "green_management",
            {"owner": Role.OWNER, "manager": Role.MANAGER, "worker": Role.WORKER, "viewer": Role.VIEWER},
        )
        agri = workspace("Team Agri", "agricultural_production", {"owner": Role.OWNER})
        other = workspace("Other Tenant", "green_management", {"other_owner": Role.OWNER})
        s.commit()

        def member(key: str, role: str | None) -> Member:
            return Member(id=users[key].id, email=users[key].email, role=role)

        return Team(
            ws=str(green.id),
            agri_ws=str(agri.id),
            other_ws=str(other.id),
            owner=member("owner", "owner"),
            manager=member("manager", "manager"),
            worker=member("worker", "worker"),
            viewer=member("viewer", "viewer"),
            outsider=member("outsider", None),
            other_owner=member("other_owner", "owner"),
            settings=settings,
        )


# --------------------------------------------------------------------------------------------------- sessions/db

# SQLite fast mode has no migrations, so the global seed species are inserted here. A PostgreSQL-mode test
# (test_db_integrity) checks that the real migration seeds at least these names.
SEED_SPECIES = [("tree", "Neem"), ("tree", "Mango"), ("tree", "Banyan"), ("crop", "Tomato"), ("crop", "Wheat")]


def _seed_species_for_sqlite(engine) -> None:
    from app.modules.catalog.models import Species

    with Session(engine) as s:
        for category, name in SEED_SPECIES:
            s.add(Species(workspace_id=None, category=category, common_name=name, attributes={"seed": True}))
        s.commit()


@dataclass
class PgEnv:
    engine: object
    settings: Settings
    schema: str
    team: Team


@pytest.fixture(scope="session")
def pg_env():
    """One migrated, throwaway schema for the whole session; dropped afterwards, with a before/after canary."""
    if not PG_MODE:
        pytest.skip("PostgreSQL mode is not active")
    schema = f"gg_test_{secrets.token_hex(4)}"
    assert SAFE_NAME.match(schema)
    base = Settings(
        env="test", database_url=postgis_url, jwt_secret=JWT_SECRET, weather_provider="mock", _env_file=None
    )
    admin = build_engine(base)
    before = snapshot_tables(admin, exclude=schema)
    settings = base.model_copy(update={"db_schema": schema})
    engine = None
    try:
        command.upgrade(alembic_cfg(postgis_url, schema), "head")
        engine = build_engine(settings)
        team = seed_team(engine, settings)
        yield PgEnv(engine=engine, settings=settings, schema=schema, team=team)
    finally:
        if engine is not None:
            engine.dispose()
        drop_test_schema(admin, schema)
        after = snapshot_tables(admin, exclude=schema)
        admin.dispose()
        assert after == before, f"tests changed tables outside {schema}: +{after - before} -{before - after}"


@dataclass
class World:
    app: object
    settings: Settings
    team: Team
    maker: sessionmaker
    mode: str
    store: MemoryObjectStore | None = None

    def db(self) -> Session:
        """A raw session for arranging/inspecting data (same connection as the app in PostgreSQL mode)."""
        return self.maker()


@pytest.fixture
def world(request):
    if PG_MODE:
        env: PgEnv = request.getfixturevalue("pg_env")
        conn = env.engine.connect()  # type: ignore[attr-defined]
        outer = conn.begin()
        maker = sessionmaker(
            bind=conn, expire_on_commit=False, autoflush=False, join_transaction_mode="create_savepoint"
        )
        settings, team, mode = env.settings, env.team, "postgres"
        engine = None
    else:
        settings = Settings(
            env="test",
            database_url="sqlite+pysqlite:///:memory:",
            jwt_secret=JWT_SECRET,
            weather_provider="mock",
            _env_file=None,
        )
        engine = build_engine(settings)
        Base.metadata.create_all(engine)
        maker = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
        team, mode = seed_team(engine, settings), "sqlite"
        _seed_species_for_sqlite(engine)

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
    store = MemoryObjectStore()
    application.dependency_overrides[get_object_store] = lambda: store
    try:
        yield World(app=application, settings=settings, team=team, maker=maker, mode=mode, store=store)
    finally:
        if PG_MODE:
            outer.rollback()
            conn.close()
        elif engine is not None:
            engine.dispose()


@pytest.fixture
def settings() -> Settings:
    """Plain settings object (no database), for tests that never touch the API."""
    return Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret=JWT_SECRET,
        weather_provider="mock",
        _env_file=None,
    )


@pytest.fixture
def app(world):
    return world.app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def team(world) -> Team:
    return world.team


class Api:
    """A caller bound to a member and a workspace; paths are relative to /api/v1/workspaces/{ws}."""

    def __init__(self, client: TestClient, headers: dict[str, str], ws: str):
        self.client, self.headers, self.ws = client, headers, ws

    def url(self, path: str) -> str:
        return f"/api/v1/workspaces/{self.ws}{path}"

    def get(self, path, **kw):
        return self.client.get(self.url(path), headers=self.headers, **kw)

    def post(self, path, json=None, **kw):
        return self.client.post(self.url(path), json=json, headers=self.headers, **kw)

    def patch(self, path, json=None, **kw):
        return self.client.patch(self.url(path), json=json, headers=self.headers, **kw)

    def delete(self, path, **kw):
        return self.client.delete(self.url(path), headers=self.headers, **kw)


@pytest.fixture
def api_for(client, team):
    """api_for(member, ws=None) -> Api. Defaults to the team's green workspace."""

    def _make(member: Member, ws: str | None = None) -> Api:
        return Api(client, team.headers(member), ws or team.ws)

    return _make


# --------------------------------------------------------------------------------- HTTP-registered actors (auth tests)


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
