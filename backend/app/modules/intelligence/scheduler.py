"""Deciding which workspaces are due for a scheduled agent run, and running them.

The simplest reliable design: the worker wakes every `worker_poll_interval_s`, asks the database which workspaces are
due, and runs them one at a time. There is no queue and no in-memory schedule, so a restarted worker loses nothing: the
schedule IS the run history (`agent_runs`). Overlap is impossible (partial unique index, see runs.py), so several
workers are safe, merely redundant.

A workspace is due when its agent schedule is enabled and
  * it has never run, or
  * its latest run succeeded at least `schedule_interval_hours` ago, or
  * its latest run failed and the retry delay has passed. The delay doubles with each consecutive failure
    (RETRY_BASE_S, 2x, 4x ...) but never exceeds the normal interval, so a persistently failing workspace is retried
    at most once per interval after the first few attempts and cannot flood the database or the weather provider.
A run still `running` makes a workspace not due (it is handled by `runs.reap_stale` if its worker died).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.core.timeutil import as_utc, utcnow
from app.modules.workspaces.models import Workspace

from . import runs
from .models import AgentRun, RunStatus, RunTrigger
from .ports import WeatherContextProvider
from .runner import AgentSettings

log = structlog.get_logger()

RETRY_BASE_S = 300  # first retry five minutes after a failed run
HISTORY_LOOKBACK = 10  # runs inspected to count consecutive failures


@dataclass(frozen=True)
class Tick:
    """What one scheduler pass did."""

    reaped: int = 0
    due: int = 0
    ran: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped_busy: int = 0


def retry_delay_s(consecutive_failures: int, interval_s: int) -> int:
    return min(RETRY_BASE_S * 2 ** max(consecutive_failures - 1, 0), interval_s)


def is_due(history: list[AgentRun], interval_s: int, now: datetime) -> bool:
    """`history` is newest first. Pure given the rows, so it is unit-testable without a worker."""
    if not history:
        return True
    latest = history[0]
    if latest.status == RunStatus.RUNNING.value:
        return False
    if latest.status == RunStatus.SUCCEEDED.value:
        return now >= as_utc(latest.started_at) + timedelta(seconds=interval_s)
    failures = 0
    for r in history:
        if r.status != RunStatus.FAILED.value:
            break
        failures += 1
    finished = as_utc(latest.finished_at or latest.started_at)
    return now >= finished + timedelta(seconds=retry_delay_s(failures, interval_s))


def due_workspaces(db: Session, now: datetime) -> list[tuple[uuid.UUID, dict]]:
    """Two queries however many workspaces there are: the workspaces, and the last few runs of each (a window
    function), so a poll does not cost a round trip per workspace against a remote database."""
    workspaces = [
        (ws_id, ws_settings or {})
        for ws_id, ws_settings in db.execute(
            select(Workspace.id, Workspace.settings).where(Workspace.archived_at.is_(None))
        )
        if AgentSettings.from_workspace(ws_settings).schedule_enabled
    ]
    if not workspaces:
        return []
    rank = (
        func.row_number()
        .over(partition_by=AgentRun.workspace_id, order_by=(AgentRun.started_at.desc(), AgentRun.id.desc()))
        .label("rn")
    )
    ranked = select(AgentRun, rank).subquery()
    recent = aliased(AgentRun, ranked)
    history: dict[uuid.UUID, list[AgentRun]] = {}
    for run in db.scalars(
        select(recent).where(ranked.c.rn <= HISTORY_LOOKBACK).order_by(recent.started_at.desc(), recent.id.desc())
    ):
        history.setdefault(run.workspace_id, []).append(run)  # newest first, as is_due expects
    return [
        (ws_id, ws_settings)
        for ws_id, ws_settings in workspaces
        if is_due(history.get(ws_id, []), AgentSettings.from_workspace(ws_settings).schedule_interval_hours * 3600, now)
    ]


def tick(
    session_factory: Callable[[], Session],
    *,
    weather: WeatherContextProvider | None,
    worker_id: str,
    stale_run_s: int,
    now: datetime | None = None,
    should_stop: Callable[[], bool] = lambda: False,
) -> Tick:
    """One pass: reap abandoned runs, then run every due workspace in turn. A failure in one workspace never stops
    the others. Checks `should_stop` between workspaces so shutdown waits at most for the run in progress."""
    now = now or utcnow()
    with session_factory() as db:
        reaped = runs.reap_stale(db, stale_after_s=stale_run_s, now=now)
        due = due_workspaces(db, now)
    ran = succeeded = failed = busy = 0
    for ws_id, ws_settings in due:
        if should_stop():
            break
        try:
            with session_factory() as db:
                claimed = runs.claim(db, ws_id, RunTrigger.SCHEDULED, worker_id=worker_id, now=now)
                if claimed is None:
                    busy += 1  # another worker (or a manual run) got there first
                    continue
                finished, result = runs.execute(db, claimed, ws_settings, weather=weather, now=now)
            ran += 1
            if result is None:
                failed += 1
            else:
                succeeded += 1
                log.info(
                    "agent_run_done",
                    workspace_id=str(ws_id),
                    run_id=str(finished.id),
                    assets=result.evaluated,
                    created=len(result.created),
                    expired=result.expired,
                )
        except Exception:  # database unreachable for this workspace: log and carry on, the next tick retries
            failed += 1
            log.exception("agent_schedule_error", workspace_id=str(ws_id))
    return Tick(reaped=reaped, due=len(due), ran=ran, succeeded=succeeded, failed=failed, skipped_busy=busy)
