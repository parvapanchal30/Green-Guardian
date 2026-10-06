from __future__ import annotations

from alembic import context
from sqlalchemy import pool

from app.core.config import get_settings
from app.core.db import build_engine
from app.models import Base

config = context.config
target_metadata = Base.metadata


def _engine():
    # A URL set programmatically (tests) wins over the environment.
    url = config.get_main_option("sqlalchemy.url")
    settings = get_settings()
    if url:
        settings = settings.model_copy(update={"database_url": url})
    return build_engine(settings)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url") or get_settings().database_url
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = _engine()
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

_ = pool  # keep import for tooling that inspects env.py
