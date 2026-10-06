from __future__ import annotations

from alembic import context

from app.core.config import get_settings
from app.core.db import build_engine
from app.models import Base

config = context.config
target_metadata = Base.metadata


def _settings():
    """Settings from the environment; `sqlalchemy.url` / `db_schema` set programmatically (tests) win."""
    settings = get_settings()
    update = {}
    if url := config.get_main_option("sqlalchemy.url"):
        update["database_url"] = url
    if schema := config.get_main_option("db_schema"):
        update["db_schema"] = schema
    return settings.model_copy(update=update)


def run_migrations_offline() -> None:
    s = _settings()
    context.configure(
        url=s.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        version_table_schema=s.db_schema if s.database_url.startswith("postgresql") else None,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    s = _settings()
    engine = build_engine(s)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            version_table_schema=s.db_schema if engine.dialect.name == "postgresql" else None,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
