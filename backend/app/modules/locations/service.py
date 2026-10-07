from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import NotFound
from app.core.pagination import Page, PageParams
from app.core.schemas import SmallDict, StrictModel

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
    return Page(items=[LocationOut.model_validate(r) for r in rows], total=total, limit=page.limit, offset=page.offset)
