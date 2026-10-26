"""Deterministic offline provider for development and tests ONLY (blocked when ENV=production).

Its output is synthetic and is labelled `source="mock"` so it can never be mistaken for real data.
"""

from __future__ import annotations

from datetime import timedelta

from app.core.timeutil import utcnow

from .domain import Forecast, HourlyPoint, Place

# Fixed places for offline development and tests (real coordinates, rounded).
MOCK_PLACES = (
    Place("Powai", "Mumbai Suburban, Maharashtra, India", 19.1176, 72.906),
    Place("Pune", "Pune, Maharashtra, India", 18.5196, 73.8553),
    Place("Nashik", "Nashik, Maharashtra, India", 19.9975, 73.7898),
    Place("New Delhi", "Delhi, India", 28.6139, 77.209),
    Place("Bengaluru", "Bengaluru Urban, Karnataka, India", 12.9716, 77.5946),
)


class MockWeatherProvider:
    key = "mock"

    def search_places(self, name: str, count: int = 8) -> tuple[Place, ...]:
        needle = name.strip().lower()
        return tuple(p for p in MOCK_PLACES if needle in p.name.lower() or needle in p.region.lower())[:count]

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
