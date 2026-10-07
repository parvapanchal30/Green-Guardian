from __future__ import annotations

import geoalchemy2  # noqa: F401  (registers the PostGIS `geometry` type so the reflected centroid columns are recognised)
from alembic import context
from sqlalchemy import text

from app.core.config import get_settings, normalize_database_url
from app.core.db import build_engine
from app.models import Base

config = context.config
target_metadata = Base.metadata

# Tables that exist in the database but are not ours: Alembic's bookkeeping table and PostGIS's reference table
# (visible through search_path). Everything else that is unexpected IS reported as drift by `alembic check`.
INFRA_TABLES = {"alembic_version", "spatial_ref_sys"}


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and reflected and name in INFRA_TABLES:
        return False
    # PostGIS-derived objects are created by migrations (generated `centroid` columns and their GiST indexes) and
    # intentionally not mapped by the ORM, so the drift check must not report them as "extra".
    if type_ == "column" and reflected and name == "centroid":
        return False
    if type_ == "index" and reflected and name is not None and name.endswith("_centroid_gist"):
        return False
    return True


def _settings():
    """Settings from the environment; `sqlalchemy.url` / `db_schema` set programmatically (tests) win."""
    settings = get_settings()
    update = {}
    if url := config.get_main_option("sqlalchemy.url"):
        # model_copy skips validators, so normalise (driver pinning) explicitly.
        update["database_url"] = normalize_database_url(url)
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
        include_object=include_object,
        version_table_schema=s.db_schema if s.database_url.startswith("postgresql") else None,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    s = _settings()
    engine = build_engine(s)
    with engine.connect() as connection:
        is_pg = engine.dialect.name == "postgresql"
        if is_pg:
            # The application schema (and so alembic_version) must exist before Alembic touches it.
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{s.db_schema}"'))
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
            version_table_schema=s.db_schema if is_pg else None,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
