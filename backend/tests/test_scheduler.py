"""Scheduled runs: which workspaces are due, retries with backoff, isolation between tenants, no duplicate work.

The scheduler is exercised with an explicit `now`, so no test sleeps and none depends on the wall clock.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from app.modules.intelligence import runner, scheduler
from app.modules.intelligence.models import AgentRun, Recommendation
from app.modules.intelligence.scheduler import RETRY_BASE_S, is_due, retry_delay_s, tick
from app.modules.workspaces.models import Workspace
from tests.helpers import make_asset
from tests.test_agent_api import age_asset

T0 = datetime(2026, 10, 18, 6, 0, tzinfo=UTC)
DAY = 24 * 3600


def run_row(status: str, *, started: datetime = T0, finished: datetime | None = None) -> AgentRun:
    return AgentRun(
        workspace_id=uuid.uuid4(),
        trigger="scheduled",
        status=status,
        started_at=started,
        finished_at=finished or (None if status == "running" else started + timedelta(seconds=5)),
    )


def do_tick(world, now, **kw):
    return tick(world.maker, weather=None, worker_id="test-worker", stale_run_s=1800, now=now, **kw)


def set_agent_settings(world, ws: str, **agent) -> None:
    with world.db() as db:
        db.execute(update(Workspace).where(Workspace.id == uuid.UUID(ws)).values(settings={"agent": agent}))
        db.commit()


def run_count(world, ws: str | None = None) -> int:
    with world.db() as db:
        q = select(func.count()).select_from(AgentRun)
        if ws:
            q = q.where(AgentRun.workspace_id == uuid.UUID(ws))
        return db.scalar(q) or 0


# ------------------------------------------------------------------------------------------- pure schedule logic


def test_a_workspace_that_never_ran_is_due():
    assert is_due([], DAY, T0)


def test_after_a_success_it_is_due_once_the_interval_has_passed():
    history = [run_row("succeeded", started=T0)]
    assert not is_due(history, DAY, T0 + timedelta(hours=23, minutes=59))
    assert is_due(history, DAY, T0 + timedelta(hours=24))


def test_a_running_run_means_not_due():
    assert not is_due([run_row("running", started=T0 - timedelta(days=9))], DAY, T0)


def test_retry_delay_doubles_and_never_exceeds_the_interval():
    assert [retry_delay_s(n, DAY) for n in (1, 2, 3, 4)] == [300, 600, 1200, 2400]
    assert retry_delay_s(30, DAY) == DAY
    assert retry_delay_s(5, 600) == 600  # a short interval caps the backoff too


def test_after_failures_it_is_retried_with_growing_delay():
    one = [run_row("failed", started=T0)]
    two = [run_row("failed", started=T0 + timedelta(minutes=6)), run_row("failed", started=T0)]
    assert not is_due(one, DAY, T0 + timedelta(seconds=RETRY_BASE_S - 10))
    assert is_due(one, DAY, T0 + timedelta(seconds=RETRY_BASE_S + 10))
    latest_finish = T0 + timedelta(minutes=6, seconds=5)
    assert not is_due(two, DAY, latest_finish + timedelta(seconds=590))
    assert is_due(two, DAY, latest_finish + timedelta(seconds=610))


def test_a_success_resets_the_failure_count():
    history = [run_row("succeeded", started=T0 + timedelta(hours=1)), run_row("failed", started=T0)]
    assert not is_due(history, DAY, T0 + timedelta(hours=2))


# ----------------------------------------------------------------------------------------------- the tick itself


def test_the_first_tick_runs_every_workspace_and_the_second_does_nothing(world, team):
    first = do_tick(world, T0)
    assert first.due == first.ran == first.succeeded == 3 and first.failed == 0
    with world.db() as db:
        runs = list(db.scalars(select(AgentRun)))
    assert {r.trigger for r in runs} == {"scheduled"} and {r.worker_id for r in runs} == {"test-worker"}
    assert {str(r.workspace_id) for r in runs} == {team.ws, team.agri_ws, team.other_ws}
    assert all(r.status == "succeeded" and r.requested_by is None for r in runs)

    again = do_tick(world, T0 + timedelta(minutes=5))
    assert again.due == again.ran == 0 and run_count(world) == 3

    next_day = do_tick(world, T0 + timedelta(hours=24, minutes=1))
    assert next_day.ran == 3 and run_count(world) == 6


def test_finding_due_workspaces_costs_two_queries_however_many_there_are(world, team):
    from sqlalchemy import event

    engine = world.maker.kw["bind"]
    with world.db() as db:
        org_id = db.scalar(select(Workspace.organization_id).where(Workspace.id == uuid.UUID(team.ws)))
        for i in range(25):
            db.add(Workspace(organization_id=org_id, name=f"Extra {i}", mode="green_management"))
        db.commit()
    do_tick(world, T0)  # every workspace now has a run, so the history query has real work to do

    seen: list[str] = []

    def record(conn, cursor, statement, *a):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        with world.db() as db:
            due = scheduler.due_workspaces(db, T0 + timedelta(hours=25))
    finally:
        event.remove(engine, "before_cursor_execute", record)
    queries = [q for q in seen if q.lstrip().upper().startswith("SELECT")]  # ignore BEGIN/SAVEPOINT bookkeeping
    assert len(due) == 28 and len(queries) == 2, (len(due), len(queries))
    with world.db() as db:
        assert scheduler.due_workspaces(db, T0 + timedelta(minutes=1)) == []


def test_a_disabled_or_archived_workspace_is_not_scheduled(world, team):
    set_agent_settings(world, team.ws, schedule_enabled=False)
    with world.db() as db:
        db.execute(update(Workspace).where(Workspace.id == uuid.UUID(team.agri_ws)).values(archived_at=T0))
        db.commit()
    t = do_tick(world, T0)
    assert t.ran == 1 and run_count(world, team.other_ws) == 1
    assert run_count(world, team.ws) == 0 and run_count(world, team.agri_ws) == 0


def test_the_interval_is_configured_per_workspace(world, team):
    set_agent_settings(world, team.ws, schedule_interval_hours=2)
    do_tick(world, T0)
    assert do_tick(world, T0 + timedelta(hours=1)).ran == 0
    t = do_tick(world, T0 + timedelta(hours=2, minutes=1))
    assert t.ran == 1 and run_count(world, team.ws) == 2  # only the 2-hourly workspace; the others wait a day


def test_one_failing_workspace_does_not_stop_the_others_and_is_retried_later(world, team, monkeypatch):
    real = runner.evaluate_workspace

    def flaky(db, workspace_id, *a, **kw):
        if str(workspace_id) == team.ws:
            raise RuntimeError("weather provider down")
        return real(db, workspace_id, *a, **kw)

    # a failed run stamps its real finish time, so this test is anchored to the real clock, not to the fixed T0
    base = datetime.now(UTC)
    monkeypatch.setattr(runner, "evaluate_workspace", flaky)
    t = do_tick(world, base)
    assert (t.ran, t.succeeded, t.failed) == (3, 2, 1)
    with world.db() as db:
        failed = db.scalar(select(AgentRun).where(AgentRun.workspace_id == uuid.UUID(team.ws)))
        assert failed is not None and failed.status == "failed" and "weather provider down" in (failed.error or "")

    assert do_tick(world, base + timedelta(minutes=2)).ran == 0  # backing off
    retry = do_tick(world, base + timedelta(minutes=6))
    assert retry.ran == 1 and retry.failed == 1 and run_count(world, team.ws) == 2
    monkeypatch.undo()
    healed = do_tick(world, base + timedelta(minutes=30))  # second failure => 10 min delay, long passed
    assert healed.ran == 1 and healed.succeeded == 1
    assert do_tick(world, base + timedelta(minutes=40)).ran == 0  # success restores the normal daily cadence


def test_repeated_runs_never_duplicate_an_open_recommendation(world, team, api_for):
    manager = api_for(team.manager)
    old = make_asset(manager, label="Neglected tree")
    age_asset(world, old["id"], 40)
    do_tick(world, T0)
    do_tick(world, T0 + timedelta(hours=25))
    do_tick(world, T0 + timedelta(hours=50))
    open_recs = manager.get("/recommendations").json()["items"]
    assert [r["rule_key"] for r in open_recs] == ["inspection_gap"]
    assert open_recs[0]["agent_run_id"] is not None and open_recs[0]["rule_version"] == 2


def test_scheduled_runs_only_touch_their_own_workspace(world, team, api_for):
    manager = api_for(team.manager)
    mine = make_asset(manager, label="Mine")
    age_asset(world, mine["id"], 40)
    other = api_for(team.other_owner, team.other_ws)
    do_tick(world, T0)
    assert len(manager.get("/recommendations").json()["items"]) == 1
    assert other.get("/recommendations").json()["items"] == []
    with world.db() as db:
        recs = list(db.scalars(select(Recommendation)))
        run_ws = {r.id: r.workspace_id for r in db.scalars(select(AgentRun))}
    assert {r.workspace_id for r in recs} == {uuid.UUID(team.ws)}
    assert all(run_ws[r.agent_run_id] == r.workspace_id for r in recs)  # a recommendation's run is in its workspace


def test_a_run_claimed_by_someone_else_is_skipped_not_duplicated(world, team, monkeypatch):
    with world.db() as db:
        db.add(AgentRun(workspace_id=uuid.UUID(team.ws), trigger="manual", status="running", started_at=T0))
        db.commit()
    monkeypatch.setattr(scheduler, "due_workspaces", lambda db, now: [(uuid.UUID(team.ws), {})])
    t = do_tick(world, T0)
    assert (t.due, t.ran, t.skipped_busy) == (1, 0, 1) and run_count(world, team.ws) == 1


def test_abandoned_runs_are_reaped_at_the_start_of_a_tick(world, team):
    with world.db() as db:
        db.add(
            AgentRun(
                workspace_id=uuid.UUID(team.ws),
                trigger="scheduled",
                status="running",
                started_at=T0 - timedelta(hours=2),
            )
        )
        db.commit()
    t = do_tick(world, T0)
    assert t.reaped == 1
    with world.db() as db:
        statuses = sorted(
            r.status for r in db.scalars(select(AgentRun).where(AgentRun.workspace_id == uuid.UUID(team.ws)))
        )
    assert "failed" in statuses  # the abandoned run was failed; the workspace then ran (or backs off) normally


def test_shutdown_is_honoured_between_workspaces(world, team):
    calls = iter([False, True, True, True])
    t = do_tick(world, T0, should_stop=lambda: next(calls))
    assert t.ran == 1 and run_count(world) == 1  # finished the run in progress, started no more
