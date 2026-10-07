"""Small factories for the vertical-slice tests. Each asserts the happy path so a test body stays about its subject."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.conftest import Api


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def ago(**kw) -> str:
    return iso(datetime.now(UTC) - timedelta(**kw))


def ahead(**kw) -> str:
    return iso(datetime.now(UTC) + timedelta(**kw))


def species_id(api: Api, name: str = "Neem") -> str:
    r = api.get("/species", params={"q": name})
    assert r.status_code == 200, r.text
    items = [s for s in r.json()["items"] if s["common_name"].lower() == name.lower()]
    assert items, f"seed species {name!r} missing"
    return items[0]["id"]


def make_location(api: Api, name: str = "Zone 1", kind: str = "zone", **over) -> dict:
    r = api.post("/locations", {"name": name, "kind": kind, **over})
    assert r.status_code == 201, r.text
    return r.json()


def make_asset(api: Api, **over) -> dict:
    payload = {"label": "Neem #1", "kind": "tree", **over}
    r = api.post("/assets", payload)
    assert r.status_code == 201, r.text
    return r.json()


def observe(api: Api, asset_id: str, **over) -> dict:
    r = api.post("/observations", {"asset_id": asset_id, "health_score": 80, **over})
    assert r.status_code == 201, r.text
    return r.json()


def make_issue(api: Api, asset_id: str, **over) -> dict:
    r = api.post("/issues", {"title": "Leaf yellowing", "asset_id": asset_id, "category": "disease", **over})
    assert r.status_code == 201, r.text
    return r.json()


def make_task(api: Api, **over) -> dict:
    r = api.post("/tasks", {"title": "Inspect canopy", "type": "inspect", **over})
    assert r.status_code == 201, r.text
    return r.json()


def resolve_body(outcome: str = "fixed", notes: str = "done", **extra) -> dict:
    return {"outcome": outcome, "notes": notes, **extra}
