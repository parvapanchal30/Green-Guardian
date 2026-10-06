from __future__ import annotations

import time
from functools import lru_cache

from app.core.config import get_settings

from .domain import Forecast, WeatherProvider
from .registry import build_provider


class WeatherService:
    """Provider-agnostic facade with a small in-process TTL cache (keyed on ~1 km rounded coordinates)."""

    def __init__(self, provider: WeatherProvider, cache_ttl_s: int = 900):
        self._provider = provider
        self._ttl = cache_ttl_s
        self._cache: dict[tuple[float, float, int], tuple[float, Forecast]] = {}

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


@lru_cache
def get_weather_service() -> WeatherService:
    s = get_settings()
    return WeatherService(build_provider(s), s.weather_cache_ttl_s)
