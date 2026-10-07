"""The `asset_states` projection (ADR-004): current health, last observation, open issue/task counts.

It is a cache of facts that live in append-only history, maintained synchronously in the same transaction as the
change that affects it, and rebuildable at any time with `rebuild_state`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import as_utc
from app.modules.issues.models import Issue
from app.modules.observations.models import Observation
from app.modules.tasks.models import OPEN_TASK_STATUSES, Task

from .health import health_band
from .models import AssetState


def ensure_state(db: Session, workspace_id: uuid.UUID, asset_id: uuid.UUID) -> AssetState:
    state = db.get(AssetState, asset_id)
    if state is None:
        state = AssetState(asset_id=asset_id, workspace_id=workspace_id, open_issue_count=0, open_task_count=0)
        db.add(state)
        db.flush()
    return state


def apply_observation(db: Session, obs: Observation) -> None:
    """Fold one observation into the projection. Back-dated entries never overwrite newer health."""
    if obs.asset_id is None:
        return
    state = ensure_state(db, obs.workspace_id, obs.asset_id)
    when = as_utc(obs.observed_at)
    if state.last_observed_at is None or when > as_utc(state.last_observed_at):
        state.last_observed_at = when
    if obs.health_score is not None and (state.health_observed_at is None or when >= as_utc(state.health_observed_at)):
        state.health_score = obs.health_score
        band = health_band(obs.health_score)
        state.health_band = band.value if band else None
        state.health_observed_at = when
    db.flush()


def refresh_counts(
    db: Session, workspace_id: uuid.UUID, asset_id: uuid.UUID, *, resolved_at: datetime | None = None
) -> None:
    """Recompute open issue/task counts for an asset (cheap, indexed, and always correct)."""
    db.flush()  # sessions run with autoflush=False: make this transaction's pending changes visible to the counts
    state = ensure_state(db, workspace_id, asset_id)
    state.open_issue_count = (
        db.scalar(
            select(func.count())
            .select_from(Issue)
            .where(Issue.workspace_id == workspace_id, Issue.asset_id == asset_id, Issue.resolved_at.is_(None))
        )
        or 0
    )
    state.open_task_count = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.workspace_id == workspace_id,
                Task.asset_id == asset_id,
                Task.status.in_([s.value for s in OPEN_TASK_STATUSES]),
            )
        )
        or 0
    )
    if resolved_at is not None:
        state.last_resolved_at = resolved_at
    db.flush()


def rebuild_state(db: Session, workspace_id: uuid.UUID, asset_id: uuid.UUID) -> AssetState:
    """Recompute the whole projection from history; used by repair jobs and by the consistency test."""
    state = ensure_state(db, workspace_id, asset_id)
    state.health_score = state.health_band = state.health_observed_at = state.last_observed_at = None
    obs = db.scalars(
        select(Observation).where(Observation.workspace_id == workspace_id, Observation.asset_id == asset_id)
    ).all()
    for o in sorted(obs, key=lambda o: as_utc(o.observed_at)):
        apply_observation(db, o)
    last_res = db.scalar(
        select(func.max(Issue.resolved_at)).where(Issue.workspace_id == workspace_id, Issue.asset_id == asset_id)
    )
    state.last_resolved_at = last_res
    refresh_counts(db, workspace_id, asset_id)
    return state
