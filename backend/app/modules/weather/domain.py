"""Provider-neutral weather domain. Business logic depends only on these types and the Protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


class WeatherUnavailable(Exception):
    """The provider could not return usable data (network, HTTP error, malformed payload)."""


@dataclass(frozen=True)
class HourlyPoint:
    time: datetime  # timezone-aware
    precipitation_mm: float | None = None
    precipitation_probability_pct: float | None = None
    temperature_c: float | None = None
    et0_mm: float | None = None
    # volumetric water content (m3/m3) by depth label, e.g. {"0_to_1cm": 0.31}
    soil_moisture: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Forecast:
    latitude: float
    longitude: float
    timezone: str
    source: str  # provider key, e.g. "open_meteo" | "mock"
    attribution: str
    fetched_at: datetime
    hourly: tuple[HourlyPoint, ...]


@dataclass(frozen=True)
class Place:
    """A named place found by a geocoder: where to ask for a forecast. Not a workspace location."""

    name: str
    region: str  # admin areas and country, e.g. "Maharashtra, India"
    latitude: float
    longitude: float


class WeatherProvider(Protocol):
    key: str

    def forecast(self, latitude: float, longitude: float, days: int) -> Forecast:
        """Hourly forecast for `days` days. Raise WeatherUnavailable on any failure."""
        ...


class PlaceFinder(Protocol):
    """Optional second capability of a provider: find places by name. Raise WeatherUnavailable on any failure."""

    def search_places(self, name: str, count: int) -> tuple[Place, ...]: ...


def expected_precipitation_mm(forecast: Forecast, start: datetime, hours: int) -> float | None:
    """Sum of forecast precipitation in [start, start+hours). None if no hourly values cover the window.

    Pure helper for the future `irrigation_defer` rule; independent of any provider.
    """
    from datetime import timedelta

    end = start + timedelta(hours=hours)
    vals = [p.precipitation_mm for p in forecast.hourly if start <= p.time < end and p.precipitation_mm is not None]
    return round(sum(vals), 2) if vals else None
