"""Engine/session construction. Pure SQLAlchemy: no provider-specific APIs."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from .config import Settings, get_settings


def build_engine(settings: Settings) -> Engine:
    url = settings.database_url
    if not url:
        raise RuntimeError("DATABASE_URL is not set (see docs/DATABASE_SETUP.md)")

    if url.startswith("sqlite"):
        # Tests / throwaway smoke runs only (ADR-007/ADR-015), never a runtime target.
        # One shared connection is only valid for a private in-memory database; a file database gets a normal pool so
        # concurrent requests do not interleave statements on a single connection.
        in_memory = ":memory:" in url or url in ("sqlite://", "sqlite+pysqlite://")
        extra = {"poolclass": StaticPool} if in_memory else {}
        engine = create_engine(url, connect_args={"check_same_thread": False}, **extra)

        @event.listens_for(engine, "connect")
        def _sqlite_fk(dbapi_conn, _):  # pragma: no cover - trivial
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine

    kwargs: dict = {"pool_pre_ping": settings.db_pool_pre_ping}
    connect_args: dict = {"connect_timeout": settings.db_connect_timeout_s}
    if "sslmode" not in make_url(url).query:
        connect_args["sslmode"] = settings.db_sslmode
    if settings.db_pool_mode == "transaction":
        # Provider transaction pooler (e.g. port 6543): no server-side prepared statements, no pooling here.
        kwargs["poolclass"] = NullPool
        connect_args["prepare_threshold"] = None
    else:
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_max_overflow
    engine = create_engine(url, connect_args=connect_args, **kwargs)

    postgis, app_schema = settings.postgis_schema, settings.db_schema
    # App schema first, PostGIS schema second. `public` is deliberately absent for a non-default app schema,
    # so an isolated test schema cannot see (or touch) real tables in `public`.
    path = f'"{app_schema}", "{postgis}"'

    @event.listens_for(engine, "connect")
    def _set_search_path(dbapi_conn, _):
        # Set per connection (not as a startup option) so poolers that reject startup params still work.
        with dbapi_conn.cursor() as cur:
            cur.execute(f"SET search_path TO {path}")
        dbapi_conn.commit()

    return engine


_engine: Engine | None = None
_sessionmaker: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = build_engine(get_settings())
        _sessionmaker = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


def get_db() -> Iterator[Session]:
    """FastAPI dependency. Services commit explicitly at the end of each use case."""
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()


def reset_engine_for_tests() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _sessionmaker = None
