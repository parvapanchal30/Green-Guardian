from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, manager_ctx, workspace_ctx
from app.core.errors import ProviderUnavailable

from . import places
from .domain import WeatherUnavailable
from .service import WeatherService, get_weather_service

router = APIRouter(tags=["weather"])


class HourlyOut(BaseModel):
    time: datetime
    precipitation_mm: float | None
    precipitation_probability_pct: float | None
    temperature_c: float | None
    et0_mm: float | None
    soil_moisture: dict[str, float]


class ForecastOut(BaseModel):
    latitude: float
    longitude: float
    timezone: str
    source: str
    attribution: str
    fetched_at: datetime
    hourly: list[HourlyOut]


@router.get("/workspaces/{ws}/weather", response_model=ForecastOut)
def get_weather(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    days: int = Query(default=3, ge=1, le=16),
    _ctx: WorkspaceContext = Depends(workspace_ctx),
    service: WeatherService = Depends(get_weather_service),
):
    """Forecast for a coordinate. (Location-based lookup replaces lat/lon once locations exist.)"""
    try:
        fc = service.forecast(lat, lon, days)
    except WeatherUnavailable as e:
        raise ProviderUnavailable("Weather provider is unavailable", code="weather_unavailable") from e
    return ForecastOut(
        latitude=fc.latitude,
        longitude=fc.longitude,
        timezone=fc.timezone,
        source=fc.source,
        attribution=fc.attribution,
        fetched_at=fc.fetched_at,
        hourly=[HourlyOut(**p.__dict__) for p in fc.hourly],
    )


# ---- "Any place": search by name, and places saved for the weather page (ADR-075)


class PlaceOut(BaseModel):
    name: str
    region: str
    latitude: float
    longitude: float


class PlaceSearchOut(BaseModel):
    source: str
    attribution: str
    items: list[PlaceOut]


@router.get("/workspaces/{ws}/weather/places/search", response_model=PlaceSearchOut)
def search_places(
    q: str = Query(min_length=2, max_length=100),
    _ctx: WorkspaceContext = Depends(workspace_ctx),
    service: WeatherService = Depends(get_weather_service),
):
    """Find a town, area or village by name (the configured provider's geocoder)."""
    try:
        found = service.search_places(q)
    except WeatherUnavailable as e:
        raise ProviderUnavailable("Place search is unavailable", code="geocoding_unavailable") from e
    source, attribution = service.source
    return PlaceSearchOut(source=source, attribution=attribution, items=[PlaceOut(**p.__dict__) for p in found])


@router.get("/workspaces/{ws}/weather/places", response_model=list[places.SavedPlaceOut])
def list_saved_places(ctx: WorkspaceContext = Depends(workspace_ctx)):
    return places.list_places(ctx)


@router.post(
    "/workspaces/{ws}/weather/places", response_model=places.SavedPlaceOut, status_code=status.HTTP_201_CREATED
)
def save_place(data: places.SavedPlaceIn, ctx: WorkspaceContext = Depends(manager_ctx), db: Session = Depends(get_db)):
    return places.save_place(db, ctx, data)


@router.delete("/workspaces/{ws}/weather/places/{place_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_place(place_id: str, ctx: WorkspaceContext = Depends(manager_ctx), db: Session = Depends(get_db)):
    places.remove_place(db, ctx, place_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
