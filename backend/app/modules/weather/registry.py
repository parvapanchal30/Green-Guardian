"""Weather provider registry: the single place that knows which concrete providers exist.

Adding a provider = write an adapter implementing `WeatherProvider`, `register_provider("key", factory)`, set
`WEATHER_PROVIDER=key`. Nothing in the agent, domain or API layers changes.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.config import Settings

from .domain import WeatherProvider
from .mock import MockWeatherProvider
from .open_meteo import OpenMeteoProvider

ProviderFactory = Callable[[Settings], WeatherProvider]

_FACTORIES: dict[str, ProviderFactory] = {
    "open_meteo": lambda s: OpenMeteoProvider(
        s.open_meteo_base_url, s.weather_timeout_s, geocoding_url=s.open_meteo_geocoding_url
    ),
    "mock": lambda s: MockWeatherProvider(),
}


class UnknownWeatherProvider(ValueError):
    pass


def register_provider(key: str, factory: ProviderFactory) -> None:
    _FACTORIES[key] = factory


def available_providers() -> list[str]:
    return sorted(_FACTORIES)


def build_provider(settings: Settings) -> WeatherProvider:
    try:
        factory = _FACTORIES[settings.weather_provider]
    except KeyError:
        raise UnknownWeatherProvider(
            f"WEATHER_PROVIDER={settings.weather_provider!r} is not registered; available: {available_providers()}"
        ) from None
    return factory(settings)
