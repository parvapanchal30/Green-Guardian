from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.deps import WorkspaceContext, workspace_ctx
from app.core.errors import ProviderUnavailable

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
