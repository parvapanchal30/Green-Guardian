from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import AppError, NotFound
from app.core.pagination import Page, PageParams
from app.core.timeutil import as_utc, utcnow
from app.modules.assets.service import get_asset
from app.modules.assets.state import apply_observation
from app.modules.audit import service as audit
from app.modules.intelligence import runner
from app.modules.intelligence.schemas import RecommendationOut

from .models import Observation
from .schemas import ObservationCreate, ObservationCreated, ObservationOut

FUTURE_TOLERANCE = timedelta(minutes=5)
MAX_BACKDATE = timedelta(days=3650)


class InvalidObservation(AppError):
    status, code = 422, "invalid_observation"


def create_observation(
    db: Session, ctx: WorkspaceContext, data: ObservationCreate, *, commit: bool = True
) -> ObservationCreated:
    """Store an observation, fold it into the asset state and run the rules. `commit=False` lets a caller that owns the
    transaction (e.g. completing a task) include it in its own unit of work."""
    asset = get_asset(db, ctx, data.asset_id)
    now = utcnow()
    observed_at = as_utc(data.observed_at) if data.observed_at else now
    if observed_at > now + FUTURE_TOLERANCE:
        raise InvalidObservation("observed_at cannot be in the future")
    if observed_at < now - MAX_BACKDATE:
        raise InvalidObservation("observed_at is too far in the past")
    from app.modules.monitor.service import check_measurements

    check_measurements(data.data)  # height_cm, girth_cm, canopy_m: numbers in range when present
    if data.health_score is None and not data.notes and not data.symptoms and not data.attachments and not data.data:
        raise InvalidObservation("an observation needs a health score, symptoms, notes, data or an attachment")
    if data.supersedes_id is not None:
        original = db.scalar(
            select(Observation).where(
                Observation.id == data.supersedes_id, Observation.workspace_id == ctx.workspace_id
            )
        )
        if original is None or original.asset_id != asset.id:
            raise InvalidObservation("supersedes_id must refer to an earlier observation of the same asset")

    obs = Observation(
        workspace_id=ctx.workspace_id,
        asset_id=asset.id,
        observed_at=observed_at,
        observer_id=ctx.user.id,
        kind=data.kind.value,
        health_score=data.health_score,
        symptoms=[s.strip() for s in data.symptoms if s.strip()],
        notes=data.notes,
        data=data.data,
        attachments=[a.model_dump(exclude_none=True) for a in data.attachments],
        supersedes_id=data.supersedes_id,
    )
    db.add(obs)
    db.flush()
    audit.record_ctx(
        db,
        ctx,
        "observation.create",
        target_type="observation",
        target_id=obs.id,
        details={"asset_id": asset.id, "kind": obs.kind, "health_score": obs.health_score},
    )
    apply_observation(db, obs)  # update the asset's current state in the same transaction
    _, recs = runner.evaluate(db, ctx, asset_ids=[asset.id], now=now)  # DETECT: rule-based checks, right away
    if commit:
        db.commit()
    else:
        db.flush()
    return ObservationCreated(
        observation=ObservationOut.model_validate(obs),
        recommendations=[RecommendationOut.model_validate(r) for r in recs],
    )


def get_observation(db: Session, ctx: WorkspaceContext, observation_id: uuid.UUID) -> Observation:
    obs = db.scalar(
        select(Observation).where(Observation.id == observation_id, Observation.workspace_id == ctx.workspace_id)
    )
    if obs is None:
        raise NotFound("Observation not found", code="observation_not_found")
    return obs


def list_observations(
    db: Session, ctx: WorkspaceContext, page: PageParams, *, asset_id: uuid.UUID | None = None
) -> Page[ObservationOut]:
    q = select(Observation).where(Observation.workspace_id == ctx.workspace_id)
    if asset_id:
        q = q.where(Observation.asset_id == asset_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(Observation.observed_at.desc(), Observation.id).limit(page.limit).offset(page.offset))
    return Page(
        items=[ObservationOut.model_validate(r) for r in rows], total=total, limit=page.limit, offset=page.offset
    )
