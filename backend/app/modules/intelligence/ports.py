"""Ports: what the Botanical Operations Agent needs from the outside world, expressed in the agent's own terms.

Dependency direction (ADR-024):

    Botanical Operations Agent (rules)  ->  WeatherContextProvider (this port)
                                                    ^
                              weather.context.ForecastWeatherContext (adapter)
                                                    |
                                  WeatherService -> WeatherProvider -> Open-Meteo | mock | future providers

The agent and its rules import nothing from `app.modules.weather` (a test enforces this), so replacing the
weather provider, or the weather service itself, never touches agent or domain logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class WeatherContext:
    """Provider-neutral weather facts at a point, as of a moment. `None` means unknown, never zero."""

    latitude: float
    longitude: float
    as_of: datetime
    source: str  # provider label for provenance in recommendation explanations
    rain_next_24h_mm: float | None = None
    max_rain_probability_pct: float | None = None
    temperature_c: float | None = None
    # volumetric water content (m3/m3) of the top soil layer
    soil_moisture_top: float | None = None


class WeatherContextProvider(Protocol):
    def context_for(self, latitude: float, longitude: float, now: datetime) -> WeatherContext | None:
        """Weather context, or None when it cannot be determined (provider down, no coverage). Must not raise."""
        ...


def get_weather_context_provider() -> WeatherContextProvider | None:
    """FastAPI dependency. The agent package imports no weather code (ADR-024), so it cannot build a provider itself:
    the application's composition root (app/main.py) overrides this to supply the real adapter. With no override the
    agent simply runs without weather (weather-dependent rules then stay silent)."""
    return None
