"""Deterministic offline provider for development and tests ONLY (blocked when ENV=production).

Its output is synthetic and is labelled `source="mock"` so it can never be mistaken for real data.
"""

from __future__ import annotations

from datetime import timedelta

from app.core.timeutil import utcnow

from .domain import Forecast, HourlyPoint


class MockWeatherProvider:
    key = "mock"

    def forecast(self, latitude: float, longitude: float, days: int) -> Forecast:
        start = utcnow().replace(minute=0, second=0, microsecond=0)
        points = tuple(
            HourlyPoint(
                time=start + timedelta(hours=h),
                precipitation_mm=1.0 if h % 24 == 12 else 0.0,
                precipitation_probability_pct=40.0 if h % 24 == 12 else 5.0,
                temperature_c=24.0,
                et0_mm=0.2,
                soil_moisture={"0_to_1cm": 0.3},
            )
            for h in range(days * 24)
        )
        return Forecast(
            latitude, longitude, "UTC", self.key, "Synthetic mock data (not real weather)", utcnow(), points
        )
