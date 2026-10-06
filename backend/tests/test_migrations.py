"""Alembic head must produce exactly the schema the ORM models describe (non-spatial tables, SQLite)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.models import Base

BACKEND = Path(__file__).resolve().parents[1]


def _cfg(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_upgrade_head_matches_models_and_downgrades_cleanly(tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'm.db'}"
    command.upgrade(_cfg(url), "head")
    engine = create_engine(url)
    assert {"users", "organizations", "workspaces", "memberships", "refresh_tokens"} <= set(
        inspect(engine).get_table_names()
    )
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": False}), Base.metadata)
    assert diff == [], f"migrations drifted from models: {diff}"
    engine.dispose()
    command.downgrade(_cfg(url), "base")
    engine = create_engine(url)
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    engine.dispose()
