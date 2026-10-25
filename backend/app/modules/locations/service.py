from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import NotFound
from app.core.pagination import Page, PageParams
from app.core.schemas import SmallDict, StrictModel
from app.modules.audit import service as audit

from .models import Location, LocationKind


class LocationCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    kind: LocationKind
    parent_id: uuid.UUID | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    attributes: SmallDict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _coords_together(self) -> LocationCreate:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be given together")
        return self


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: LocationKind
    parent_id: uuid.UUID | None
    latitude: float | None
    longitude: float | None
    attributes: dict
    # In lists: living assets placed here, how many of them are at risk or critical, active recurring inspections.
    assets: int = 0
    needs_attention: int = 0
    schedules: int = 0


def get_location(db: Session, ctx: WorkspaceContext, location_id: uuid.UUID) -> Location:
    loc = db.scalar(
        select(Location).where(
            Location.id == location_id, Location.workspace_id == ctx.workspace_id, Location.archived_at.is_(None)
        )
    )
    if loc is None:
        raise NotFound("Location not found", code="location_not_found")
    return loc


def create_location(db: Session, ctx: WorkspaceContext, data: LocationCreate) -> Location:
    if data.parent_id is not None:
        get_location(db, ctx, data.parent_id)  # same workspace, not archived (and the composite FK backs this up)
    loc = Location(
        workspace_id=ctx.workspace_id,
        name=data.name,
        kind=data.kind.value,
        parent_id=data.parent_id,
        latitude=data.latitude,
        longitude=data.longitude,
        attributes=data.attributes,
    )
    db.add(loc)
    db.flush()
    audit.record_ctx(
        db,
        ctx,
        "location.create",
        target_type="location",
        target_id=loc.id,
        details={"name": loc.name, "kind": loc.kind},
    )
    db.commit()
    return loc


def list_locations(
    db: Session, ctx: WorkspaceContext, page: PageParams, kind: LocationKind | None = None
) -> Page[LocationOut]:
    q = select(Location).where(Location.workspace_id == ctx.workspace_id, Location.archived_at.is_(None))
    if kind:
        q = q.where(Location.kind == kind.value)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(Location.name, Location.id).limit(page.limit).offset(page.offset)).all()
    counts = _counts(db, ctx, [r.id for r in rows])
    items = [LocationOut.model_validate(r).model_copy(update=counts.get(r.id, {})) for r in rows]
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


def _counts(db: Session, ctx: WorkspaceContext, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    """Living assets per location (not archived, not out of the lifecycle), those at risk or critical, and active
    recurring inspections. Three grouped queries, whatever the number of locations."""
    if not ids:
        return {}
    from app.modules.assets import lifecycle as lc
    from app.modules.assets.models import AssetState, BiologicalAsset
    from app.modules.schedules.models import InspectionSchedule

    out: dict[uuid.UUID, dict[str, int]] = {i: {"assets": 0, "needs_attention": 0, "schedules": 0} for i in ids}
    living = (
        BiologicalAsset.workspace_id == ctx.workspace_id,
        BiologicalAsset.location_id.in_(ids),
        BiologicalAsset.archived_at.is_(None),
        BiologicalAsset.current_stage.notin_(lc.EXIT_STAGES),
    )
    for loc, n in db.execute(
        select(BiologicalAsset.location_id, func.count()).where(*living).group_by(BiologicalAsset.location_id)
    ):
        if loc is not None:
            out[loc]["assets"] = int(n)
    attention = (
        select(BiologicalAsset.location_id, func.count())
        .join(AssetState, AssetState.asset_id == BiologicalAsset.id)
        .where(*living, AssetState.health_band.in_(("at_risk", "critical")))
        .group_by(BiologicalAsset.location_id)
    )
    for loc, n in db.execute(attention):
        if loc is not None:
            out[loc]["needs_attention"] = int(n)
    schedules = (
        select(InspectionSchedule.location_id, func.count())
        .where(
            InspectionSchedule.workspace_id == ctx.workspace_id,
            InspectionSchedule.location_id.in_(ids),
            InspectionSchedule.active.is_(True),
        )
        .group_by(InspectionSchedule.location_id)
    )
    for loc, n in db.execute(schedules):
        if loc is not None:
            out[loc]["schedules"] = int(n)
    return out
