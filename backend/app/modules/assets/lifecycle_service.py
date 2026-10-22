"""Recording and reading an asset's lifecycle (ADR-055).

`biological_assets.current_stage` is a projection of the latest `lifecycle_events` row. Every change goes through
`record`, which, in ONE transaction: locks the asset row (two concurrent changes cannot both pass the checks), validates the
transition against the workspace's template, appends the event, updates the projection and writes the audit entry.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import Conflict, Forbidden, Unprocessable
from app.core.timeutil import as_utc, utcnow
from app.modules.audit import service as audit
from app.modules.workspaces.models import Role

from . import lifecycle as lc
from .models import BiologicalAsset, LifecycleEvent
from .schemas import (
    AssetLifecycleOut,
    LifecycleEventOut,
    LifecycleRecord,
    LifecycleTemplateOut,
    StageChoice,
)

FUTURE_TOLERANCE = timedelta(minutes=5)
HISTORY_LIMIT = 500


def _choice(key: str, kind: str) -> StageChoice:
    return StageChoice(key=key, label=lc.LABELS.get(key, key), kind=kind, manager_only=key in lc.MANAGER_ONLY_EXITS)


def template(ctx: WorkspaceContext) -> LifecycleTemplateOut:
    mode = ctx.workspace.mode
    return LifecycleTemplateOut(
        mode=mode,
        stages=[_choice(s, "stage") for s in lc.stages_for(mode)],
        exits_individual=[_choice(s, "exit") for s in lc.exits_for("individual")],
        exits_population=[_choice(s, "exit") for s in lc.exits_for("population")],
        rules=[
            "Stages advance; you may skip ahead (a mature tree is registered as mature).",
            "Moving back, or reinstating an exited asset, is a correction: a manager records it with a written reason.",
            "Dead and failed are observations; removed and replaced are management decisions and need a manager.",
            "An asset that has exited no longer appears in inspections, agent suggestions or the active counts.",
            "History is append-only: nothing is edited or deleted, corrections are new entries.",
        ],
    )


def initial_stage(ctx: WorkspaceContext, requested: str | None) -> str:
    stage = requested or "planted"
    allowed = lc.stages_for(ctx.workspace.mode)
    if stage not in allowed:
        raise Unprocessable(
            f"{stage!r} is not a starting stage for this workspace; use one of: {', '.join(allowed)}",
            code="invalid_stage",
            extra={"allowed": list(allowed)},
        )
    return stage


def initial_entered_at(planted_at) -> datetime:
    """When the first event is dated: the planting date if it is known and not in the future, otherwise now."""
    now = utcnow()
    if planted_at is None:
        return now
    return min(datetime.combine(planted_at, datetime.min.time(), tzinfo=now.tzinfo), now)


def record_initial(db: Session, ctx: WorkspaceContext, asset: BiologicalAsset, entered_at: datetime) -> None:
    db.add(
        LifecycleEvent(
            workspace_id=ctx.workspace_id,
            asset_id=asset.id,
            stage=asset.current_stage,
            previous_stage=None,
            entered_at=entered_at,
            source="manual",
            correction=False,
            note=None,
            actor_id=ctx.user.id,
        )
    )


def _out(e: LifecycleEvent) -> LifecycleEventOut:
    return LifecycleEventOut(
        id=e.id,
        asset_id=e.asset_id,
        stage=e.stage,
        stage_label=lc.LABELS.get(e.stage, e.stage),
        previous_stage=e.previous_stage,
        entered_at=e.entered_at,
        recorded_at=e.created_at,
        source=e.source,
        correction=e.correction,
        note=e.note,
        actor_id=e.actor_id,
    )


def _latest(db: Session, ctx: WorkspaceContext, asset_id: uuid.UUID) -> LifecycleEvent | None:
    return db.scalar(
        select(LifecycleEvent)
        .where(LifecycleEvent.workspace_id == ctx.workspace_id, LifecycleEvent.asset_id == asset_id)
        .order_by(LifecycleEvent.entered_at.desc(), LifecycleEvent.id.desc())
        .limit(1)
    )


def view(db: Session, ctx: WorkspaceContext, asset: BiologicalAsset) -> AssetLifecycleOut:
    rows = db.scalars(
        select(LifecycleEvent)
        .where(LifecycleEvent.workspace_id == ctx.workspace_id, LifecycleEvent.asset_id == asset.id)
        .order_by(LifecycleEvent.entered_at.desc(), LifecycleEvent.id.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    mode = ctx.workspace.mode
    choices = lc.next_choices(mode, asset.tracking_mode, asset.current_stage)
    return AssetLifecycleOut(
        asset_id=asset.id,
        current_stage=asset.current_stage,
        is_active=not lc.is_exit(asset.current_stage),
        next_choices=[_choice(k, "exit" if lc.is_exit(k) else "stage") for k in choices],
        history=[_out(e) for e in rows],
    )


def record(db: Session, ctx: WorkspaceContext, asset: BiologicalAsset, data: LifecycleRecord) -> AssetLifecycleOut:
    is_manager = ctx.has_role(Role.MANAGER)
    # Serialise concurrent changes to the same asset and read its current stage fresh from the database.
    db.refresh(asset, with_for_update=True)
    current = asset.current_stage

    problem = lc.check_transition(
        ctx.workspace.mode, asset.tracking_mode, current, data.stage, correction=data.correction
    )
    if problem:
        extra = {"allowed": list(problem.allowed), "current_stage": current}
        if problem.kind == "invalid":
            raise Unprocessable(problem.message, code=problem.code, extra=extra)
        raise Conflict(problem.message, code=problem.code, extra=extra)

    note = (data.note or "").strip() or None
    if data.correction:
        if not is_manager:
            raise Forbidden("Only a manager can record a correction", code="correction_requires_manager")
        if note is None or len(note) < lc.MIN_CORRECTION_NOTE:
            raise Unprocessable(
                f"A correction needs a written reason of at least {lc.MIN_CORRECTION_NOTE} characters",
                code="correction_reason_required",
            )
    elif data.stage in lc.MANAGER_ONLY_EXITS and not is_manager:
        raise Forbidden(f"Only a manager can record {data.stage!r}", code="exit_requires_manager")

    now = utcnow()
    entered_at = as_utc(data.entered_at) if data.entered_at else now
    if entered_at > now + FUTURE_TOLERANCE:
        raise Unprocessable("entered_at cannot be in the future", code="entered_in_future")
    last = _latest(db, ctx, asset.id)
    if last is not None and entered_at < as_utc(last.entered_at):
        raise Unprocessable(
            f"entered_at cannot be earlier than the previous stage change ({as_utc(last.entered_at).isoformat()})",
            code="entered_before_previous",
        )

    db.add(
        LifecycleEvent(
            workspace_id=ctx.workspace_id,
            asset_id=asset.id,
            stage=data.stage,
            previous_stage=current,
            entered_at=entered_at,
            source="manual",
            correction=data.correction,
            note=note,
            actor_id=ctx.user.id,
        )
    )
    asset.current_stage = data.stage
    audit.record_ctx(
        db,
        ctx,
        "asset.lifecycle.record",
        target_type="asset",
        target_id=asset.id,
        details={
            "from": current,
            "to": data.stage,
            "correction": data.correction,
            "entered_at": entered_at.isoformat(),
        },
    )
    db.commit()
    return view(db, ctx, asset)
