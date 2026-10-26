"""The weather page's "Any place" tab (ADR-075): search places by name, save places for the weather page."""

from __future__ import annotations

import httpx
import pytest

from app.modules.weather.domain import WeatherUnavailable
from app.modules.weather.open_meteo import OpenMeteoProvider, parse_places
from app.modules.weather.service import WeatherService

GEO = {
    "results": [
        {"name": "Powai", "latitude": 19.1176, "longitude": 72.906, "admin1": "Maharashtra", "country": "India"},
        {"name": "Powai", "latitude": 25.4, "longitude": 81.8, "country": "India"},
    ]
}


def test_open_meteo_geocoding_parameters_and_parsing():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url.copy_with(query=None))
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=GEO)

    prov = OpenMeteoProvider(
        "https://api.open-meteo.com/v1/forecast",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        geocoding_url="https://geocoding-api.open-meteo.com/v1/search",
    )
    found = prov.search_places("Powai", 8)
    assert seen["url"] == "https://geocoding-api.open-meteo.com/v1/search"
    assert seen["name"] == "Powai" and seen["count"] == "8"
    assert [(p.name, p.region) for p in found] == [("Powai", "Maharashtra, India"), ("Powai", "India")]
    assert parse_places({}) == ()  # no match: Open-Meteo leaves "results" out


@pytest.mark.parametrize("bad", [{"results": [{"name": "x"}]}, {"results": "nope"}])
def test_malformed_geocoding_payloads_are_unavailable(bad):
    with pytest.raises(WeatherUnavailable):
        parse_places(bad)


def test_search_endpoint_uses_the_configured_provider_and_labels_it(api_for, team):
    r = api_for(team.viewer).get("/weather/places/search", params={"q": "pune"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "mock" and "not a real search" in body["attribution"]
    assert [p["name"] for p in body["items"]] == ["Pune"]
    assert api_for(team.viewer).get("/weather/places/search", params={"q": "x"}).status_code == 422


def test_search_failure_is_503_without_provider_details(app, api_for, team):
    from app.modules.weather.service import get_weather_service

    class Down:
        key = "down"

        def forecast(self, *a):
            raise WeatherUnavailable("boom")

        def search_places(self, *a):
            raise WeatherUnavailable("geocoder internals")

    app.dependency_overrides[get_weather_service] = lambda: WeatherService(Down(), 1)
    r = api_for(team.viewer).get("/weather/places/search", params={"q": "pune"})
    assert r.status_code == 503 and r.json()["code"] == "geocoding_unavailable"
    assert "internals" not in r.text


def test_managers_save_and_remove_places_everyone_reads_them(api_for, team):
    manager, worker, viewer = api_for(team.manager), api_for(team.worker), api_for(team.viewer)
    place = {"name": "Pune", "region": "Maharashtra, India", "latitude": 18.51963, "longitude": 73.85535}
    assert worker.post("/weather/places", place).status_code == 403
    r = manager.post("/weather/places", place)
    assert r.status_code == 201, r.text
    saved = r.json()
    assert saved["latitude"] == 18.5196 and saved["name"] == "Pune"
    assert [p["id"] for p in viewer.get("/weather/places").json()] == [saved["id"]]
    assert manager.post("/weather/places", place).json()["code"] == "place_exists"
    assert manager.post("/weather/places", {**place, "latitude": 91}).status_code == 422

    audit = manager.get("/audit", params={"action": "weather.place.save"}).json()
    assert audit["total"] == 1

    assert worker.delete(f"/weather/places/{saved['id']}").status_code == 403
    assert manager.delete(f"/weather/places/{saved['id']}").status_code == 204
    assert viewer.get("/weather/places").json() == []
    assert manager.delete(f"/weather/places/{saved['id']}").status_code == 404


def test_saving_keeps_the_other_workspace_settings(api_for, team):
    owner = api_for(team.owner)
    assert (
        owner.client.patch(
            f"/api/v1/workspaces/{team.ws}", json={"settings": {"agent": {"x": 1}}}, headers=owner.headers
        ).status_code
        == 200
    )
    assert owner.post("/weather/places", {"name": "Nashik", "latitude": 20.0, "longitude": 73.79}).status_code == 201
    ws = owner.client.get(f"/api/v1/workspaces/{team.ws}", headers=owner.headers).json()
    assert ws["settings"]["agent"] == {"x": 1} and len(ws["settings"]["weather_places"]) == 1


def test_places_stay_in_their_workspace(api_for, team):
    mine = api_for(team.manager)
    saved = mine.post("/weather/places", {"name": "Pune", "latitude": 18.52, "longitude": 73.86}).json()
    other = api_for(team.other_owner, team.other_ws)
    assert other.get("/weather/places").json() == []
    assert other.delete(f"/weather/places/{saved['id']}").status_code == 404
    assert len(mine.get("/weather/places").json()) == 1
    assert api_for(team.other_owner).get("/weather/places").status_code in (403, 404)  # not a member here
