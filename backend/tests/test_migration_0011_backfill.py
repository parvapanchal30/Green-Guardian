"""Migration 0011 on data that already exists: every asset gets exactly one initial lifecycle event carrying its current
stage, so "current_stage equals the latest event" holds for old rows too (SQLite; the PostgreSQL trigger/RLS parts of the
migration are exercised by the PostgreSQL-mode suite and CI)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

BACKEND = Path(__file__).resolve().parents[1]


def _cfg(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _asset(conn, ws, **over):
    row = {
        "id": uuid.uuid4().hex,
        "workspace_id": ws,
        "kind": "tree",
        "tracking_mode": "individual",
        "label": "x",
        "current_stage": "planted",
        "attributes": "{}",
        "planted_at": None,
        "created_at": "2026-03-01 10:00:00",
        "updated_at": "2026-03-01 10:00:00",
        **over,
    }
    cols = ", ".join(row)
    conn.execute(text(f"INSERT INTO biological_assets ({cols}) VALUES ({', '.join(':' + c for c in row)})"), row)
    return row["id"]


def test_existing_assets_get_one_initial_event_each(tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'm.db'}"
    command.upgrade(_cfg(url), "0010")
    engine = create_engine(url)
    ws, org = uuid.uuid4().hex, uuid.uuid4().hex
    future = (datetime.now(UTC) + timedelta(days=90)).date().isoformat()
    with engine.begin() as conn:
        stamp = "2026-01-01 00:00:00"
        conn.execute(
            text(
                "INSERT INTO organizations (id, name, slug, created_at, updated_at) VALUES (:i, 'Org', 'org', :t, :t)"
            ),
            {"i": org, "t": stamp},
        )
        conn.execute(
            text(
                "INSERT INTO workspaces (id, organization_id, name, mode, timezone, settings, capabilities, key_counters,"
                " created_at, updated_at) VALUES (:i, :o, 'W', 'green_management', 'UTC', '{}', '{}', '{}', :t, :t)"
            ),
            {"i": ws, "o": org, "t": stamp},
        )
        dated = _asset(conn, ws, label="dated", current_stage="mature", planted_at="2020-05-01")
        undated = _asset(conn, ws, label="undated")
        planned = _asset(conn, ws, label="planned", planted_at=future)
        legacy = _asset(conn, ws, label="legacy", current_stage="not_a_stage")
    engine.dispose()

    command.upgrade(_cfg(url), "head")
    engine = create_engine(url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT asset_id, stage, previous_stage, entered_at, source, correction, note FROM lifecycle_events")
        ).all()
        by_asset = {r[0]: r for r in rows}
        assert len(rows) == 4 and set(by_asset) == {dated, undated, planned, legacy}
        for r in rows:
            assert r.source == "system" and not r.correction and r.previous_stage is None and r.note
        assert by_asset[dated].stage == "mature" and str(by_asset[dated].entered_at).startswith("2020-05-01")
        assert by_asset[undated].stage == "planted" and str(by_asset[undated].entered_at).startswith("2026-03-01")
        assert by_asset[legacy].stage == "planted"  # an unknown legacy stage is normalised, not carried into the CHECK
        entered = datetime.fromisoformat(str(by_asset[planned].entered_at)).replace(tzinfo=UTC)
        assert entered <= datetime.now(UTC)  # a planting date in the future never dates an event in the future
    engine.dispose()

    command.downgrade(_cfg(url), "0010")
    engine = create_engine(url)
    assert "lifecycle_events" not in inspect(engine).get_table_names()
    with engine.connect() as conn:  # the assets themselves are untouched
        assert conn.execute(text("SELECT count(*) FROM biological_assets")).scalar() == 4
    engine.dispose()


# ------------------------------------------------------------------ the same migration on real PostgreSQL

import secrets  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.db import build_engine  # noqa: E402
from tests.conftest import JWT_SECRET, postgis_url, requires_pg_mode  # noqa: E402
from tests.pgsupport import alembic_cfg, drop_test_schema  # noqa: E402


@requires_pg_mode
def test_backfill_trigger_rls_and_downgrade_on_postgresql():
    """Own throwaway schema (named like the test fixture's, dropped afterwards): rows exist at 0010, 0011 backfills them,
    the table is append-only and row-level-security protected, and the downgrade leaves the assets alone."""
    schema = f"gg_test_{secrets.token_hex(4)}"
    base = Settings(
        env="test", database_url=postgis_url, jwt_secret=JWT_SECRET, weather_provider="mock", _env_file=None
    )
    admin = build_engine(base)
    engine = None
    try:
        command.upgrade(alembic_cfg(postgis_url, schema), "0010")
        engine = build_engine(base.model_copy(update={"db_schema": schema}))
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, slug, created_at, updated_at) VALUES (gen_random_uuid(), 'O', 'o-' || :s, now(), now())"
                ),
                {"s": schema},
            )
            conn.execute(
                text(
                    "INSERT INTO workspaces (id, organization_id, name, mode, timezone, settings, capabilities, key_counters, created_at, updated_at) "
                    "SELECT gen_random_uuid(), id, 'W', 'green_management', 'UTC', '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, now(), now() FROM organizations"
                )
            )
            for label, stage, planted in (
                ("dated", "mature", "2020-05-01"),
                ("undated", "planted", None),
                ("planned", "planted", "2999-01-01"),
            ):
                conn.execute(
                    text(
                        "INSERT INTO biological_assets (id, workspace_id, kind, tracking_mode, label, current_stage, attributes, planted_at, created_at, updated_at) "
                        "SELECT gen_random_uuid(), id, 'tree', 'individual', :l, :s, '{}'::jsonb, CAST(:p AS date), now(), now() FROM workspaces"
                    ),
                    {"l": label, "s": stage, "p": planted},
                )
        engine.dispose()

        command.upgrade(alembic_cfg(postgis_url, schema), "head")
        engine = build_engine(base.model_copy(update={"db_schema": schema}))
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT a.label, e.stage, e.entered_at, e.source, e.previous_stage FROM lifecycle_events e "
                    "JOIN biological_assets a ON a.id = e.asset_id AND a.workspace_id = e.workspace_id ORDER BY a.label"
                )
            ).all()
            assert [(r.label, r.stage, r.source, r.previous_stage) for r in rows] == [
                ("dated", "mature", "system", None),
                ("planned", "planted", "system", None),
                ("undated", "planted", "system", None),
            ]
            by = {r.label: r.entered_at for r in rows}
            assert str(by["dated"]).startswith("2020-05-01")
            assert by["planned"] <= datetime.now(UTC)  # a future planting date never dates an event in the future
            for table in (
                "lifecycle_events",
                "harvest_records",
            ):  # head also created 0012's table, with the same protections
                assert (
                    conn.execute(
                        text(
                            "SELECT relrowsecurity FROM pg_class WHERE relname = :t AND relnamespace = to_regnamespace(:s)"
                        ),
                        {"t": table, "s": schema},
                    ).scalar()
                    is True
                )
            assert (
                conn.execute(
                    text(
                        "SELECT relrowsecurity FROM pg_class WHERE relname = 'lifecycle_events' AND relnamespace = to_regnamespace(:s)"
                    ),
                    {"s": schema},
                ).scalar()
                is True
            )
            assert (
                conn.execute(
                    text(
                        "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid WHERE c.relname = 'lifecycle_events' AND NOT t.tgisinternal"
                    )
                ).scalar()
                >= 1
            )
        with engine.connect() as conn, pytest.raises(DBAPIError, match="append-only"):
            conn.execute(text("UPDATE lifecycle_events SET note = 'edited'"))
        engine.dispose()

        command.downgrade(alembic_cfg(postgis_url, schema), "0010")
        engine = build_engine(base.model_copy(update={"db_schema": schema}))
        with engine.connect() as conn:
            assert conn.execute(text("SELECT to_regclass(:n)"), {"n": f"{schema}.lifecycle_events"}).scalar() is None
            assert conn.execute(text("SELECT to_regclass(:n)"), {"n": f"{schema}.harvest_records"}).scalar() is None
            assert conn.execute(text("SELECT count(*) FROM biological_assets")).scalar() == 3
    finally:
        if engine is not None:
            engine.dispose()
        drop_test_schema(admin, schema)
        admin.dispose()
