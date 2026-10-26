"""Saved weather places (ADR-075): points a workspace wants a forecast for, kept in the workspace's settings.

A saved place is only a name and a coordinate for the weather page. It is not a workspace location: it holds no
plants and changes nothing else. Every query is the current workspace's (`ctx.workspace`).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import Conflict, NotFound
from app.modules.audit import service as audit

SETTINGS_KEY = "weather_places"
MAX_PLACES = 20


class SavedPlaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    region: str | None = Field(default=None, max_length=200)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class SavedPlaceOut(SavedPlaceIn):
    id: str


def list_places(ctx: WorkspaceContext) -> list[SavedPlaceOut]:
    raw = (ctx.workspace.settings or {}).get(SETTINGS_KEY) or []
    return [SavedPlaceOut(**p) for p in raw if isinstance(p, dict)]


def _store(db: Session, ctx: WorkspaceContext, places: list[SavedPlaceOut]) -> None:
    # A new dict so the JSON column is seen as changed; other settings are kept as they are.
    ctx.workspace.settings = {**(ctx.workspace.settings or {}), SETTINGS_KEY: [p.model_dump() for p in places]}


def save_place(db: Session, ctx: WorkspaceContext, data: SavedPlaceIn) -> SavedPlaceOut:
    places = list_places(ctx)
    if len(places) >= MAX_PLACES:
        raise Conflict(f"A workspace keeps at most {MAX_PLACES} weather places", code="too_many_places")
    lat, lon = round(data.latitude, 4), round(data.longitude, 4)
    if any(abs(p.latitude - lat) < 0.001 and abs(p.longitude - lon) < 0.001 for p in places):
        raise Conflict("This place is already saved", code="place_exists")
    place = SavedPlaceOut(
        id=str(uuid.uuid4()), name=data.name.strip(), region=(data.region or None), latitude=lat, longitude=lon
    )
    _store(db, ctx, [*places, place])
    audit.record_ctx(
        db, ctx, "weather.place.save", target_type="workspace", target_id=ctx.workspace_id, details={"name": place.name}
    )
    db.commit()
    return place


def remove_place(db: Session, ctx: WorkspaceContext, place_id: str) -> None:
    places = list_places(ctx)
    keep = [p for p in places if p.id != place_id]
    if len(keep) == len(places):
        raise NotFound("No such saved place", code="place_not_found")
    _store(db, ctx, keep)
    audit.record_ctx(
        db, ctx, "weather.place.remove", target_type="workspace", target_id=ctx.workspace_id, details={"id": place_id}
    )
    db.commit()
