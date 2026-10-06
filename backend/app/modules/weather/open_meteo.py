"""Open-Meteo adapter (https://open-meteo.com/en/docs).

Terms: the free API is for NON-COMMERCIAL use; commercial deployments need an API key and the
customer endpoint (risk R-WX-1 in docs/DATABASE_SETUP.md). Attribution is returned with every forecast.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.core.timeutil import utcnow

from .domain import Forecast, HourlyPoint, WeatherUnavailable

ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"
SOIL_DEPTHS = ("0_to_1cm", "1_to_3cm", "3_to_9cm", "9_to_27cm", "27_to_81cm")
HOURLY_VARS = (
    "temperature_2m",
    "precipitation",
    "precipitation_probability",
    "et0_fao_evapotranspiration",
    *[f"soil_moisture_{d}" for d in SOIL_DEPTHS],
)


class OpenMeteoProvider:
    key = "open_meteo"

    def __init__(self, base_url: str, timeout_s: float = 8.0, client: httpx.Client | None = None):
        self._base_url = base_url
        self._client = client or httpx.Client(timeout=timeout_s)

    def forecast(self, latitude: float, longitude: float, days: int) -> Forecast:
        params: dict[str, str | int | float] = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(HOURLY_VARS),
            "forecast_days": days,
            "timezone": "auto",
        }
        try:
            resp = self._client.get(self._base_url, params=params)
            resp.raise_for_status()
            payload = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            raise WeatherUnavailable(f"Open-Meteo request failed: {e}") from e
        return parse_forecast(payload)


def parse_forecast(payload: dict) -> Forecast:
    try:
        hourly = payload["hourly"]
        times = hourly["time"]
        tz_name = payload.get("timezone", "UTC")
        tz = ZoneInfo(tz_name)
        points = []
        for i, t in enumerate(times):

            def col(name: str, _i: int = i):
                series = hourly.get(name)
                return None if series is None or series[_i] is None else float(series[_i])

            soil = {d: v for d in SOIL_DEPTHS if (v := col(f"soil_moisture_{d}")) is not None}
            points.append(
                HourlyPoint(
                    time=datetime.fromisoformat(t).replace(tzinfo=tz),
                    precipitation_mm=col("precipitation"),
                    precipitation_probability_pct=col("precipitation_probability"),
                    temperature_c=col("temperature_2m"),
                    et0_mm=col("et0_fao_evapotranspiration"),
                    soil_moisture=soil,
                )
            )
        return Forecast(
            latitude=float(payload["latitude"]),
            longitude=float(payload["longitude"]),
            timezone=tz_name,
            source=OpenMeteoProvider.key,
            attribution=ATTRIBUTION,
            fetched_at=utcnow(),
            hourly=tuple(points),
        )
    except (KeyError, TypeError, ValueError, IndexError) as e:
        raise WeatherUnavailable(f"Unexpected Open-Meteo payload: {e}") from e
