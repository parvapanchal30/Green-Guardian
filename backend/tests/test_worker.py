"""The worker process: one pass, graceful stop, heartbeat health check, weather wiring. No sleeping, no network."""

from __future__ import annotations

import threading
import time

from sqlalchemy import func, select

from app import worker
from app.modules.intelligence.models import AgentRun
from app.modules.intelligence.ports import WeatherContextProvider
from app.modules.weather.context import ForecastWeatherContext


def wire(monkeypatch, world, tmp_path):
    monkeypatch.setattr(worker, "get_settings", lambda: world.settings)
    monkeypatch.setattr(worker, "get_sessionmaker", lambda: world.maker)
    monkeypatch.setattr(worker, "build_weather", lambda settings: None)
    monkeypatch.setattr(worker.housekeeping, "run", lambda: {"stub": True})
    monkeypatch.setattr(worker, "HEARTBEAT", tmp_path / "heartbeat")


def test_once_runs_due_workspaces_and_exits(world, monkeypatch, tmp_path):
    wire(monkeypatch, world, tmp_path)
    worker.run(threading.Event(), once=True)
    with world.db() as db:
        assert db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.trigger == "scheduled")) == 3
    worker.run(threading.Event(), once=True)  # nothing is due a second later
    with world.db() as db:
        assert db.scalar(select(func.count()).select_from(AgentRun)) == 3


def test_a_stop_signal_before_the_loop_starts_does_no_work(world, monkeypatch, tmp_path):
    wire(monkeypatch, world, tmp_path)
    stop = threading.Event()
    stop.set()
    worker.run(stop)
    with world.db() as db:
        assert db.scalar(select(func.count()).select_from(AgentRun)) == 0


def test_a_transient_failure_does_not_kill_the_worker(world, monkeypatch, tmp_path):
    wire(monkeypatch, world, tmp_path)

    def broken(*a, **kw):
        raise ConnectionError("database restarting")

    monkeypatch.setattr(worker.scheduler, "tick", broken)
    worker.run(threading.Event(), once=True)  # logs and returns; does not raise


def test_the_loop_waits_between_passes_and_stops_promptly(world, monkeypatch, tmp_path):
    wire(monkeypatch, world, tmp_path)
    stop = threading.Event()
    passes = []
    real = worker.scheduler.tick

    def counting(*a, **kw):
        passes.append(1)
        stop.set()  # request shutdown during the first pass
        return real(*a, **kw)

    monkeypatch.setattr(worker.scheduler, "tick", counting)
    started = time.monotonic()
    worker.run(stop)
    assert len(passes) == 1 and time.monotonic() - started < 10  # did not wait out the poll interval


def test_heartbeat_health_check(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, "HEARTBEAT", tmp_path / "hb")
    assert worker.healthy(60) is False  # never started
    worker.beat()
    assert worker.healthy(60) is True
    (tmp_path / "hb").write_text(str(time.time() - 500))
    assert worker.healthy(60) is False
    (tmp_path / "hb").write_text("garbage")
    assert worker.healthy(60) is False


def test_the_worker_wires_the_weather_adapter_to_the_agents_port(settings):
    provider: WeatherContextProvider | None = worker.build_weather(settings)
    assert isinstance(provider, ForecastWeatherContext)  # the real wiring; tests above stub it out


def test_a_labelled_worker_records_its_label_and_creates_due_recurring_tasks(
    world, team, api_for, monkeypatch, tmp_path
):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    from app.modules.schedules.models import ScheduleOccurrence
    from tests.helpers import ahead, make_asset

    wire(monkeypatch, world, tmp_path)
    m = api_for(team.manager)
    tree = make_asset(m)
    assert (
        m.post("/schedules", {"asset_id": tree["id"], "interval_days": 7, "first_due_at": ahead(days=3)}).status_code
        == 201
    )
    with world.db() as db:  # the first inspection falls due
        db.execute(
            text("UPDATE inspection_schedules SET next_due_at = :t"), {"t": datetime.now(UTC) - timedelta(minutes=1)}
        )
        db.commit()
    worker.run(threading.Event(), once=True, label="gg-demo")
    with world.db() as db:
        workers = set(db.scalars(select(AgentRun.worker_id)))
        created = db.scalar(
            select(func.count()).select_from(ScheduleOccurrence).where(ScheduleOccurrence.outcome == "created")
        )
    assert workers and all(w.startswith("gg-demo@") for w in workers)
    assert created == 1
