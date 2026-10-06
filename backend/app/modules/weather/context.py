"""Adapter from the provider-neutral weather service to the agent's `WeatherContextProvider` port."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.modules.intelligence.ports import WeatherContext

from .domain import Forecast, WeatherUnavailable
from .service import WeatherService


def summarize_forecast(fc: Forecast, now: datetime) -> WeatherContext | None:
    """Context for the hour containing `now`, looking 24 h ahead. None if the forecast does not cover `now`."""
    now = now if now.tzinfo else now.replace(tzinfo=UTC)
    idx = next((i for i, p in enumerate(fc.hourly) if p.time <= now < p.time + timedelta(hours=1)), None)
    if idx is None:
        return None
    window = fc.hourly[idx : idx + 24]
    rain = [p.precipitation_mm for p in window if p.precipitation_mm is not None]
    probs = [p.precipitation_probability_pct for p in window if p.precipitation_probability_pct is not None]
    here = fc.hourly[idx]
    return WeatherContext(
        latitude=fc.latitude,
        longitude=fc.longitude,
        as_of=now,
        source=fc.source,
        rain_next_24h_mm=round(sum(rain), 2) if rain else None,
        max_rain_probability_pct=max(probs) if probs else None,
        temperature_c=here.temperature_c,
        soil_moisture_top=here.soil_moisture.get("0_to_1cm"),
    )


class ForecastWeatherContext:
    """Implements `WeatherContextProvider` on top of any `WeatherService` (hence any `WeatherProvider`)."""

    def __init__(self, service: WeatherService, horizon_days: int = 2):
        self._service = service
        self._days = horizon_days

    def context_for(self, latitude: float, longitude: float, now: datetime) -> WeatherContext | None:
        try:
            fc = self._service.forecast(latitude, longitude, self._days)
        except WeatherUnavailable:
            return None  # the agent degrades gracefully: weather-dependent rules simply do not fire
        return summarize_forecast(fc, now)
