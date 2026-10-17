"""Agent run lifecycle: claim, execute, finish or fail, reap abandoned runs.

Concurrency: `claim` inserts a `running` row; a partial unique index (one running row per workspace) makes the second
claimant fail, whichever process it is in, so manual and scheduled runs can never overlap and several workers are safe.
A worker that dies leaves a `running` row; `reap_stale` fails such rows after a timeout so the workspace is not stuck.
Failure: an exception during evaluation rolls the evaluation back, marks the run `failed` with a short error (no stack
trace, no secrets) and records a failure audit event; it never leaves a half-applied evaluation behind.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.timeutil import as_utc, utcnow
from app.modules.audit import service as audit

from . import runner
from .models import AgentRun, RunStatus, RunTrigger
from .ports import WeatherContextProvider

log = structlog.get_logger()

_SECRET = re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization|key)(\s*[=:]\s*)\S+")


def safe_error(exc: Exception) -> str:
    """A short, secret-free description of a failure for the run history (type and message, no stack trace)."""
    message = _SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}[redacted]", str(exc))
    return f"{type(exc).__name__}: {message[:300]}"


def claim(
    db: Session,
    workspace_id: uuid.UUID,
    trigger: RunTrigger,
    *,
    requested_by: uuid.UUID | None = None,
    worker_id: str | None = None,
    now: datetime | None = None,
) -> AgentRun | None:
    """Start a run, or return None if one is already running for this workspace. Commits the claim."""
    run = AgentRun(
        workspace_id=workspace_id,
        trigger=trigger.value,
        status=RunStatus.RUNNING.value,
        requested_by=requested_by,
        worker_id=worker_id,
        started_at=now or utcnow(),
    )
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError:
        return None
    db.commit()
    return run


def execute(
    db: Session,
    run: AgentRun,
    workspace_settings: dict | None,
    *,
    weather: WeatherContextProvider | None,
    now: datetime | None = None,
    asset_ids: list[uuid.UUID] | None = None,
) -> tuple[AgentRun, runner.EvaluationResult | None]:
    """Evaluate the run's workspace and finish the run row. Never raises for evaluation errors: they are recorded."""
    run_id, workspace_id, requested_by, trigger = run.id, run.workspace_id, run.requested_by, run.trigger
    now = now or utcnow()
    try:
        result = runner.evaluate_workspace(
            db, workspace_id, workspace_settings, now=now, asset_ids=asset_ids, weather=weather, run_id=run_id
        )
        run.status = RunStatus.SUCCEEDED.value
        run.finished_at = utcnow()
        run.evaluated_assets = result.evaluated
        run.findings = result.findings
        run.recommendations_created = len(result.created)
        run.recommendations_expired = result.expired
        run.rules = result.rules
        run.diagnostics = result.diagnostics
        audit.record(
            db,
            action="agent.run",
            workspace_id=workspace_id,
            actor_id=requested_by,
            target_type="agent_run",
            target_id=run_id,
            details={
                "trigger": trigger,
                "assets_evaluated": result.evaluated,
                "recommendations_created": len(result.created),
                "recommendations_expired": result.expired,
            },
        )
        db.commit()
        return run, result
    except Exception as exc:
        db.rollback()  # discard the partial evaluation entirely
        error = safe_error(exc)
        log.error("agent_run_failed", run_id=str(run_id), workspace_id=str(workspace_id), error=error)
        failed = db.get(AgentRun, run_id)
        assert failed is not None
        failed.status = RunStatus.FAILED.value
        failed.finished_at = utcnow()
        failed.error = error
        audit.record(
            db,
            action="agent.run",
            workspace_id=workspace_id,
            actor_id=requested_by,
            target_type="agent_run",
            target_id=run_id,
            outcome="failure",
            details={"trigger": trigger, "error_type": type(exc).__name__},
        )
        db.commit()
        return failed, None


def reap_stale(db: Session, *, stale_after_s: int, now: datetime | None = None) -> int:
    """Fail runs that have been `running` for longer than `stale_after_s` (their worker is presumed dead)."""
    now = now or utcnow()
    cutoff = now - timedelta(seconds=stale_after_s)
    running = db.scalars(select(AgentRun).where(AgentRun.status == RunStatus.RUNNING.value))
    stale = [r for r in running if as_utc(r.started_at) < cutoff]
    for r in stale:
        r.status = RunStatus.FAILED.value
        r.finished_at = now
        r.error = f"abandoned: still running after {stale_after_s} s (the worker presumably stopped)"
        audit.record(
            db,
            action="agent.run",
            workspace_id=r.workspace_id,
            target_type="agent_run",
            target_id=r.id,
            outcome="failure",
            details={"trigger": r.trigger, "reason": "abandoned"},
        )
    if stale:
        db.commit()
    return len(stale)
