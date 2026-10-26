from __future__ import annotations

import time
from functools import lru_cache

from app.core.config import get_settings

from .domain import Forecast, Place, WeatherProvider, WeatherUnavailable
from .registry import build_provider


class WeatherService:
    """Provider-agnostic facade with a small in-process TTL cache (keyed on ~1 km rounded coordinates)."""

    def __init__(self, provider: WeatherProvider, cache_ttl_s: int = 900):
        self._provider = provider
        self._ttl = cache_ttl_s
        self._cache: dict[tuple[float, float, int], tuple[float, Forecast]] = {}
        self._places: dict[str, tuple[float, tuple[Place, ...]]] = {}

    @property
    def provider_key(self) -> str:
        return self._provider.key

    def forecast(self, latitude: float, longitude: float, days: int = 3) -> Forecast:
        key = (round(latitude, 2), round(longitude, 2), days)
        hit = self._cache.get(key)
        now = time.monotonic()
        if hit and now - hit[0] < self._ttl:
            return hit[1]
        fc = self._provider.forecast(latitude, longitude, days)  # raises WeatherUnavailable
        self._cache[key] = (now, fc)
        return fc

    @property
    def source(self) -> tuple[str, str]:
        """Provider key and the attribution to show with search results."""
        if self._provider.key == "mock":
            return "mock", "Fixed example places (not a real search)"
        return self._provider.key, "Place search by Open-Meteo.com (CC BY 4.0)"

    def search_places(self, name: str, count: int = 8) -> tuple[Place, ...]:
        finder = getattr(self._provider, "search_places", None)
        if finder is None:
            raise WeatherUnavailable(f"provider {self._provider.key!r} cannot search places")
        key = f"{name.strip().lower()}|{count}"
        hit = self._places.get(key)
        now = time.monotonic()
        if hit and now - hit[0] < self._ttl:
            return hit[1]
        found = finder(name.strip(), count)
        self._places[key] = (now, found)
        return found


@lru_cache
def get_weather_service() -> WeatherService:
    s = get_settings()
    return WeatherService(build_provider(s), s.weather_cache_ttl_s)
