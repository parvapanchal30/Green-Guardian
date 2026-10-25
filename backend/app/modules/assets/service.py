from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import Conflict, NotFound
from app.core.pagination import Page, PageParams
from app.core.timeutil import utcnow
from app.modules.audit import service as audit
from app.modules.catalog.models import Species
from app.modules.catalog.service import get_visible_species
from app.modules.harvests.models import HarvestRecord  # noqa: E402
from app.modules.issues.models import Issue, IssueStatusHistory
from app.modules.locations.models import Location
from app.modules.locations.service import get_location
from app.modules.observations.models import Observation
from app.modules.tasks.models import Task, TaskStatusHistory

from . import lifecycle as lc
from . import lifecycle_service
from .models import AssetKind, AssetState, BiologicalAsset, HealthBand, LifecycleEvent
from .schemas import AssetCreate, AssetOut, AssetUpdate, StateOut, TimelineEvent
from .state import ensure_state


def get_asset(
    db: Session, ctx: WorkspaceContext, asset_id: uuid.UUID, *, include_archived: bool = False
) -> BiologicalAsset:
    q = select(BiologicalAsset).where(BiologicalAsset.id == asset_id, BiologicalAsset.workspace_id == ctx.workspace_id)
    if not include_archived:
        q = q.where(BiologicalAsset.archived_at.is_(None))
    asset = db.scalar(q)
    if asset is None:
        raise NotFound("Asset not found", code="asset_not_found")
    return asset


def to_out(
    asset: BiologicalAsset, state: AssetState | None, species_name: str | None, location_name: str | None
) -> AssetOut:
    st = state or AssetState(open_issue_count=0, open_task_count=0)
    return AssetOut(
        id=asset.id,
        label=asset.label,
        kind=AssetKind(asset.kind),
        tracking_mode=asset.tracking_mode,  # type: ignore[arg-type]
        tag_code=asset.tag_code,
        estimated_count=asset.estimated_count,
        current_stage=asset.current_stage,
        is_active=not lc.is_exit(asset.current_stage),
        species_id=asset.species_id,
        species_name=species_name,
        location_id=asset.location_id,
        location_name=location_name,
        latitude=asset.latitude,
        longitude=asset.longitude,
        planted_at=asset.planted_at,
        attributes=asset.attributes,
        notes=asset.notes,
        created_at=asset.created_at,
        archived_at=asset.archived_at,
        state=StateOut(
            health_score=st.health_score,
            health_band=st.health_band,  # type: ignore[arg-type]
            health_observed_at=st.health_observed_at,
            last_observed_at=st.last_observed_at,
            open_issue_count=st.open_issue_count or 0,
            open_task_count=st.open_task_count or 0,
            last_resolved_at=st.last_resolved_at,
        ),
    )


def profile(db: Session, ctx: WorkspaceContext, asset: BiologicalAsset) -> AssetOut:
    species = db.get(Species, asset.species_id) if asset.species_id else None
    location = db.get(Location, asset.location_id) if asset.location_id else None
    state = db.get(AssetState, asset.id)
    return to_out(asset, state, species.common_name if species else None, location.name if location else None)


def _check_tag_free(
    db: Session, ctx: WorkspaceContext, tag_code: str | None, *, except_id: uuid.UUID | None = None
) -> None:
    if tag_code is None:
        return
    q = select(BiologicalAsset.id).where(
        BiologicalAsset.workspace_id == ctx.workspace_id, BiologicalAsset.tag_code == tag_code
    )
    if except_id:
        q = q.where(BiologicalAsset.id != except_id)
    if db.scalar(q):
        raise Conflict(f"tag_code {tag_code!r} is already used in this workspace", code="tag_code_taken")


AUDITED_FIELDS = ["label", "location_id", "species_id", "tag_code", "estimated_count", "latitude", "longitude", "notes"]


def create_asset(db: Session, ctx: WorkspaceContext, data: AssetCreate) -> AssetOut:
    if data.location_id:
        get_location(db, ctx, data.location_id)
    if data.species_id:
        get_visible_species(db, ctx, data.species_id)
    _check_tag_free(db, ctx, data.tag_code)
    stage = lifecycle_service.initial_stage(ctx, data.stage)
    asset = BiologicalAsset(
        workspace_id=ctx.workspace_id,
        location_id=data.location_id,
        species_id=data.species_id,
        kind=data.kind.value,
        tracking_mode=data.tracking_mode.value,
        label=data.label,
        tag_code=data.tag_code,
        estimated_count=data.estimated_count,
        latitude=data.latitude,
        longitude=data.longitude,
        planted_at=data.planted_at,
        current_stage=stage,
        attributes=data.attributes,
        notes=data.notes,
        created_by=ctx.user.id,
    )
    db.add(asset)
    try:
        db.flush()
    except IntegrityError as e:  # lost a race against another request using the same tag
        db.rollback()
        raise Conflict("tag_code is already used in this workspace", code="tag_code_taken") from e
    ensure_state(db, ctx.workspace_id, asset.id)
    lifecycle_service.record_initial(db, ctx, asset, lifecycle_service.initial_entered_at(data.planted_at))
    audit.record_ctx(
        db,
        ctx,
        "asset.create",
        target_type="asset",
        target_id=asset.id,
        details={"label": asset.label, "kind": asset.kind, "location_id": asset.location_id},
    )
    db.commit()
    return profile(db, ctx, asset)


def get_profile(db: Session, ctx: WorkspaceContext, asset_id: uuid.UUID) -> AssetOut:
    return profile(db, ctx, get_asset(db, ctx, asset_id))


def list_assets(
    db: Session,
    ctx: WorkspaceContext,
    page: PageParams,
    *,
    kind: AssetKind | None = None,
    location_id: uuid.UUID | None = None,
    health_band: HealthBand | None = None,
    q: str | None = None,
    has_open_issue: bool | None = None,
    stage: str | None = None,
    active: bool | None = None,
) -> Page[AssetOut]:
    stmt = (
        select(BiologicalAsset, AssetState, Species.common_name, Location.name)
        .outerjoin(AssetState, AssetState.asset_id == BiologicalAsset.id)
        .outerjoin(Species, Species.id == BiologicalAsset.species_id)
        .outerjoin(Location, Location.id == BiologicalAsset.location_id)
        .where(BiologicalAsset.workspace_id == ctx.workspace_id, BiologicalAsset.archived_at.is_(None))
    )
    if kind:
        stmt = stmt.where(BiologicalAsset.kind == kind.value)
    if location_id:
        stmt = stmt.where(BiologicalAsset.location_id == location_id)
    if health_band:
        stmt = stmt.where(AssetState.health_band == health_band.value)
    if stage:
        stmt = stmt.where(BiologicalAsset.current_stage == stage)
    if active is True:
        stmt = stmt.where(BiologicalAsset.current_stage.notin_(lc.EXIT_STAGES))
    if active is False:
        stmt = stmt.where(BiologicalAsset.current_stage.in_(lc.EXIT_STAGES))
    if has_open_issue is True:
        stmt = stmt.where(AssetState.open_issue_count > 0)
    if has_open_issue is False:
        stmt = stmt.where(or_(AssetState.open_issue_count == 0, AssetState.asset_id.is_(None)))
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(BiologicalAsset.label).like(like),
                func.lower(func.coalesce(BiologicalAsset.tag_code, "")).like(like),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.execute(
        stmt.order_by(BiologicalAsset.label, BiologicalAsset.id).limit(page.limit).offset(page.offset)
    ).all()
    return Page(
        items=[to_out(a, st, sp, loc) for a, st, sp, loc in rows], total=total, limit=page.limit, offset=page.offset
    )


def update_asset(db: Session, ctx: WorkspaceContext, asset_id: uuid.UUID, data: AssetUpdate) -> AssetOut:
    asset = get_asset(db, ctx, asset_id)
    before = {f: getattr(asset, f) for f in AUDITED_FIELDS}
    sent = data.model_fields_set
    if "location_id" in sent:
        if data.location_id:
            get_location(db, ctx, data.location_id)
        asset.location_id = data.location_id
    if "species_id" in sent:
        if data.species_id:
            get_visible_species(db, ctx, data.species_id)
        asset.species_id = data.species_id
    if "tag_code" in sent:
        _check_tag_free(db, ctx, data.tag_code, except_id=asset.id)
        asset.tag_code = data.tag_code
    if "label" in sent and data.label is not None:
        asset.label = data.label
    if "estimated_count" in sent:
        if asset.tracking_mode == "individual" and data.estimated_count is not None:
            raise Conflict("estimated_count only applies to population assets", code="not_population_asset")
        asset.estimated_count = data.estimated_count
    if "latitude" in sent or "longitude" in sent:
        lat = data.latitude if "latitude" in sent else asset.latitude
        lon = data.longitude if "longitude" in sent else asset.longitude
        if (lat is None) != (lon is None):
            raise Conflict("latitude and longitude must be set together", code="coords_pair")
        asset.latitude, asset.longitude = lat, lon
    if "attributes" in sent and data.attributes is not None:
        asset.attributes = data.attributes
    if "notes" in sent:
        asset.notes = data.notes
    changed = audit.changes(before, {f: getattr(asset, f) for f in AUDITED_FIELDS}, AUDITED_FIELDS)
    if changed:
        audit.record_ctx(db, ctx, "asset.update", target_type="asset", target_id=asset.id, details={"changes": changed})
    db.commit()
    return profile(db, ctx, asset)


def archive_asset(db: Session, ctx: WorkspaceContext, asset_id: uuid.UUID) -> None:
    """Soft delete: history (observations, issues, tasks) is preserved."""
    asset = get_asset(db, ctx, asset_id)
    asset.archived_at = utcnow()
    audit.record_ctx(db, ctx, "asset.archive", target_type="asset", target_id=asset.id, details={"label": asset.label})
    db.commit()


def timeline(db: Session, ctx: WorkspaceContext, asset_id: uuid.UUID, limit: int = 200) -> list[TimelineEvent]:
    """What happened to this asset, newest first: observations plus every issue and task state change."""
    get_asset(db, ctx, asset_id, include_archived=True)
    events: list[TimelineEvent] = []
    for o in db.scalars(
        select(Observation)
        .where(Observation.workspace_id == ctx.workspace_id, Observation.asset_id == asset_id)
        .order_by(Observation.observed_at.desc())
        .limit(limit)
    ):
        bits = [f"health {o.health_score:g}" if o.health_score is not None else None, ", ".join(o.symptoms) or None]
        events.append(
            TimelineEvent(
                at=o.observed_at,
                type="observation",
                ref_id=o.id,
                key=None,
                title=f"Observation ({o.kind})",
                detail=" · ".join(b for b in [*bits, o.notes] if b) or None,
                actor_id=o.observer_id,
            )
        )
    for ih, key, title in db.execute(
        select(IssueStatusHistory, Issue.key, Issue.title)
        .join(
            Issue, (Issue.workspace_id == IssueStatusHistory.workspace_id) & (Issue.id == IssueStatusHistory.issue_id)
        )
        .where(Issue.workspace_id == ctx.workspace_id, Issue.asset_id == asset_id)
        .order_by(IssueStatusHistory.at.desc())
        .limit(limit)
    ):
        what = f"opened as {ih.to_state}" if ih.from_state is None else f"{ih.from_state} → {ih.to_state}"
        events.append(
            TimelineEvent(
                at=ih.at,
                type="issue",
                ref_id=ih.issue_id,
                key=key,
                title=f"{key} {title}",
                detail=what + (f" — {ih.note}" if ih.note else ""),
                actor_id=ih.actor_id,
            )
        )
    for th, key, title in db.execute(
        select(TaskStatusHistory, Task.key, Task.title)
        .join(Task, (Task.workspace_id == TaskStatusHistory.workspace_id) & (Task.id == TaskStatusHistory.task_id))
        .where(Task.workspace_id == ctx.workspace_id, Task.asset_id == asset_id)
        .order_by(TaskStatusHistory.at.desc())
        .limit(limit)
    ):
        what = f"created as {th.to_status}" if th.from_status is None else f"{th.from_status} → {th.to_status}"
        events.append(
            TimelineEvent(
                at=th.at,
                type="task",
                ref_id=th.task_id,
                key=key,
                title=f"{key} {title}",
                detail=what + (f" — {th.note}" if th.note else ""),
                actor_id=th.actor_id,
            )
        )
    for le in db.scalars(
        select(LifecycleEvent)
        .where(LifecycleEvent.workspace_id == ctx.workspace_id, LifecycleEvent.asset_id == asset_id)
        .order_by(LifecycleEvent.entered_at.desc())
        .limit(limit)
    ):
        what = (
            f"entered {lc.LABELS.get(le.stage, le.stage)}"
            if le.previous_stage is None
            else (f"{lc.LABELS.get(le.previous_stage, le.previous_stage)} → {lc.LABELS.get(le.stage, le.stage)}")
        )
        events.append(
            TimelineEvent(
                at=le.entered_at,
                type="lifecycle",
                ref_id=le.id,
                key=None,
                title=("Correction: " if le.correction else "Lifecycle: ") + what,
                detail=le.note,
                actor_id=le.actor_id,
            )
        )
    for hr in db.scalars(
        select(HarvestRecord)
        .where(HarvestRecord.workspace_id == ctx.workspace_id, HarvestRecord.asset_id == asset_id)
        .order_by(HarvestRecord.harvested_at.desc())
        .limit(limit)
    ):
        events.append(
            TimelineEvent(
                at=hr.harvested_at,
                type="harvest",
                ref_id=hr.id,
                key=None,
                title=("Harvest correction: " if hr.supersedes_id else "Harvest: ") + f"{hr.quantity:g} {hr.unit}",
                detail=" · ".join(b for b in (hr.grade, hr.note) if b) or None,
                actor_id=hr.recorded_by,
            )
        )
    from app.modules.actions.models import ActionRecord
    from app.modules.actions.service import KIND_LABELS

    for ar in db.scalars(
        select(ActionRecord)
        .where(ActionRecord.workspace_id == ctx.workspace_id, ActionRecord.asset_id == asset_id)
        .order_by(ActionRecord.performed_at.desc())
        .limit(limit)
    ):
        what = KIND_LABELS.get(ar.kind, ar.kind).capitalize()
        amount = f"{ar.quantity:g} {ar.unit}" if ar.quantity is not None else None
        prefix = "Action withdrawn: " if ar.withdrawn else "Action correction: " if ar.supersedes_id else "Action: "
        events.append(
            TimelineEvent(
                at=ar.performed_at,
                type="action",
                ref_id=ar.id,
                key=None,
                title=prefix + what,
                detail=" · ".join(b for b in (ar.product, amount, ar.note) if b) or None,
                actor_id=ar.performed_by,
            )
        )
    events.sort(key=lambda e: e.at, reverse=True)
    return events[:limit]
