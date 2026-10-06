from __future__ import annotations

from datetime import datetime, timedelta

import httpx
import pytest

from app.core.errors import ProviderUnavailable  # noqa: F401
from app.core.timeutil import utcnow
from app.modules.weather.domain import Forecast, HourlyPoint, WeatherUnavailable, expected_precipitation_mm
from app.modules.weather.open_meteo import OpenMeteoProvider, parse_forecast
from app.modules.weather.service import WeatherService

PAYLOAD = {
    "latitude": 19.2,
    "longitude": 72.97,
    "timezone": "Asia/Kolkata",
    "hourly": {
        "time": ["2026-10-06T00:00", "2026-10-06T01:00", "2026-10-06T02:00"],
        "temperature_2m": [27.1, 26.8, None],
        "precipitation": [0.0, 2.5, 4.0],
        "precipitation_probability": [10, 80, 90],
        "et0_fao_evapotranspiration": [0.1, 0.1, 0.2],
        "soil_moisture_0_to_1cm": [0.31, 0.33, 0.35],
        "soil_moisture_9_to_27cm": [0.28, None, 0.29],
    },
}


def test_parse_forecast_maps_columns_and_timezone():
    fc = parse_forecast(PAYLOAD)
    assert fc.source == "open_meteo" and "Open-Meteo" in fc.attribution
    assert len(fc.hourly) == 3
    p = fc.hourly[1]
    assert p.time.utcoffset() == timedelta(hours=5, minutes=30)
    assert p.precipitation_mm == 2.5 and p.precipitation_probability_pct == 80.0
    assert p.soil_moisture == {"0_to_1cm": 0.33}  # missing depths are omitted, not zero
    assert fc.hourly[2].temperature_c is None


@pytest.mark.parametrize("bad", [{}, {"hourly": {}}, {"latitude": 1, "longitude": 2, "hourly": {"time": ["bogus"]}}])
def test_parse_forecast_rejects_malformed_payloads(bad):
    with pytest.raises(WeatherUnavailable):
        parse_forecast(bad)


def test_open_meteo_provider_sends_documented_parameters():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=PAYLOAD)

    prov = OpenMeteoProvider(
        "https://api.open-meteo.com/v1/forecast", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    fc = prov.forecast(19.2, 72.97, 3)
    assert seen["latitude"] == "19.2" and seen["longitude"] == "72.97"
    assert seen["forecast_days"] == "3" and seen["timezone"] == "auto"
    assert "precipitation" in seen["hourly"] and "soil_moisture_0_to_1cm" in seen["hourly"]
    assert fc.hourly


@pytest.mark.parametrize("status", [400, 429, 500])
def test_provider_http_errors_become_weather_unavailable(status):
    transport = httpx.MockTransport(lambda r: httpx.Response(status, json={"error": True, "reason": "x"}))
    prov = OpenMeteoProvider("https://x.invalid/v1/forecast", client=httpx.Client(transport=transport))
    with pytest.raises(WeatherUnavailable):
        prov.forecast(1, 2, 1)


def test_expected_precipitation_window_and_missing_data():
    fc = parse_forecast(PAYLOAD)
    start = fc.hourly[0].time
    assert expected_precipitation_mm(fc, start, 3) == 6.5
    assert expected_precipitation_mm(fc, start, 2) == 2.5
    assert expected_precipitation_mm(fc, start + timedelta(days=5), 3) is None


class CountingProvider:
    key = "counting"

    def __init__(self):
        self.calls = 0

    def forecast(self, lat, lon, days):
        self.calls += 1
        return Forecast(lat, lon, "UTC", self.key, "t", utcnow(), (HourlyPoint(datetime(2026, 1, 1)),))


def test_service_caches_by_rounded_coordinates_and_days():
    prov = CountingProvider()
    svc = WeatherService(prov, cache_ttl_s=60)
    svc.forecast(19.2001, 72.9701, 3)
    svc.forecast(19.2049, 72.9699, 3)  # same ~1 km cell
    assert prov.calls == 1
    svc.forecast(19.2, 72.97, 5)  # different horizon
    svc.forecast(20.0, 72.97, 3)  # different place
    assert prov.calls == 3


def test_service_does_not_cache_failures():
    class Flaky:
        key = "flaky"
        n = 0

        def forecast(self, *a):
            Flaky.n += 1
            if Flaky.n == 1:
                raise WeatherUnavailable("down")
            return Forecast(0, 0, "UTC", "flaky", "t", utcnow(), ())

    svc = WeatherService(Flaky(), 60)
    with pytest.raises(WeatherUnavailable):
        svc.forecast(1, 1)
    assert svc.forecast(1, 1).source == "flaky"


def test_endpoint_returns_forecast_with_source_label(make_actor):
    a = make_actor("a@example.com")
    ws = a.create_workspace()
    r = a.get(f"/api/v1/workspaces/{ws}/weather?lat=19.2&lon=72.9&days=2")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "mock" and "not real" in body["attribution"].lower()
    assert len(body["hourly"]) == 48


def test_endpoint_validates_coordinates_and_maps_provider_failure(app, make_actor):
    from app.modules.weather.service import get_weather_service

    a = make_actor("a@example.com")
    ws = a.create_workspace()
    assert a.get(f"/api/v1/workspaces/{ws}/weather?lat=95&lon=0").status_code == 422
    assert a.get(f"/api/v1/workspaces/{ws}/weather?lat=0&lon=0&days=99").status_code == 422

    class Down:
        key = "down"

        def forecast(self, *a):
            raise WeatherUnavailable("boom")

    app.dependency_overrides[get_weather_service] = lambda: WeatherService(Down(), 1)
    r = a.get(f"/api/v1/workspaces/{ws}/weather?lat=1&lon=1")
    assert r.status_code == 503 and r.json()["code"] == "weather_unavailable"
    assert "boom" not in r.text  # provider internals are not leaked
