"""MONITOR / OBSERVE: observations are evidence, immutable, and they drive the asset's current state."""

from __future__ import annotations

import pytest

from tests.helpers import ago, ahead, make_asset, observe

PHOTO = {
    "name": "leaf.jpg",
    "content_type": "image/jpeg",
    "url": "https://example.com/p/leaf.jpg",
    "caption": "underside",
}


def test_recording_a_health_observation_updates_the_asset_state(api_for, team):
    worker = api_for(team.worker)
    asset = make_asset(worker)
    out = observe(worker, asset["id"], health_score=82, symptoms=["leaf_spot"], notes="mild spotting")
    o = out["observation"]
    assert o["health_score"] == 82 and o["symptoms"] == ["leaf_spot"] and o["observer_id"] == str(team.worker.id)
    assert o["kind"] == "health" and o["source"] == "human"

    st = worker.get(f"/assets/{asset['id']}").json()["state"]
    assert st["health_score"] == 82 and st["health_band"] == "healthy"
    assert st["last_observed_at"] is not None and st["health_observed_at"] is not None


@pytest.mark.parametrize(
    "score,band",
    [(100, "healthy"), (70, "healthy"), (69.9, "at_risk"), (40, "at_risk"), (39.9, "critical"), (0, "critical")],
)
def test_health_bands_follow_the_documented_thresholds(api_for, team, score, band):
    api = api_for(team.worker)
    a = make_asset(api)
    observe(api, a["id"], health_score=score)
    assert api.get(f"/assets/{a['id']}").json()["state"]["health_band"] == band


def test_a_back_dated_observation_never_overwrites_newer_health(api_for, team):
    api = api_for(team.worker)
    a = make_asset(api)
    observe(api, a["id"], health_score=75, observed_at=ago(hours=1))
    observe(api, a["id"], health_score=20, observed_at=ago(days=10))  # an old paper note entered late
    st = api.get(f"/assets/{a['id']}").json()["state"]
    assert st["health_score"] == 75 and st["health_band"] == "healthy"
    # both observations remain in the record
    assert api.get("/observations", params={"asset_id": a["id"]}).json()["total"] == 2


def test_observation_without_a_health_score_does_not_touch_health_but_marks_inspection(api_for, team):
    api = api_for(team.worker)
    a = make_asset(api)
    observe(api, a["id"], health_score=60, observed_at=ago(days=2))
    observe(api, a["id"], health_score=None, notes="watered, soil moist", kind="inspection")
    st = api.get(f"/assets/{a['id']}").json()["state"]
    assert st["health_score"] == 60  # unchanged
    assert st["last_observed_at"] > st["health_observed_at"]  # but the asset was inspected more recently


@pytest.mark.parametrize(
    "extra,code",
    [
        ({"health_score": None}, "invalid_observation"),  # nothing recorded at all
        ({"observed_at": ahead(hours=2)}, "invalid_observation"),  # the future
        ({"observed_at": "1900-01-01T00:00:00Z"}, "invalid_observation"),
    ],
)
def test_invalid_observations_are_rejected_with_a_reason(api_for, team, extra, code):
    api = api_for(team.worker)
    a = make_asset(api)
    r = api.post("/observations", {"asset_id": a["id"], **extra})
    assert r.status_code == 422 and r.json()["code"] == code


@pytest.mark.parametrize(
    "extra",
    [
        {"health_score": 101},
        {"health_score": -1},
        {"kind": "mood"},
        {"symptoms": ["x"] * 21},
        {"notes": "n" * 5001},
        {"attachments": [{**PHOTO, "content_type": "application/x-sh"}]},  # not an image
        {"attachments": [{**PHOTO, "url": "http://insecure.example/x.jpg"}]},  # not https
        {"attachments": [{"name": "a.jpg", "content_type": "image/png"}]},  # no url
        {
            "attachments": [{**PHOTO, "storage_key": "other-workspace-id/asset/blob.jpg"}]
        },  # clients cannot name a stored object
        {"attachments": [PHOTO] * 11},
        {"bogus": True},
    ],
)
def test_observation_schema_validation(api_for, team, extra):
    api = api_for(team.worker)
    a = make_asset(api)
    r = api.post("/observations", {"asset_id": a["id"], "health_score": 50, **extra})
    assert r.status_code == 422 and r.json()["code"] == "validation_error"


def test_photo_evidence_metadata_is_stored(api_for, team):
    api = api_for(team.worker)
    a = make_asset(api)
    second = {"name": "b.png", "content_type": "image/png", "url": "https://example.com/b.png", "caption": "bark"}
    o = observe(api, a["id"], attachments=[PHOTO, second])
    atts = o["observation"]["attachments"]
    assert atts == [PHOTO, second] and all("storage_key" not in x for x in atts)
    assert api.get(f"/observations/{o['observation']['id']}").json()["attachments"][0]["name"] == "leaf.jpg"


def test_observations_are_immutable_through_the_api(api_for, team, app):
    api = api_for(team.manager)
    a = make_asset(api)
    oid = observe(api, a["id"])["observation"]["id"]
    for method in ("put", "patch", "delete"):
        r = getattr(api.client, method)(api.url(f"/observations/{oid}"), headers=api.headers)
        assert r.status_code == 405, (method, r.status_code)
    paths = app.openapi()["paths"]
    assert set(paths["/api/v1/workspaces/{ws}/observations/{observation_id}"]) == {"get"}


def test_a_correction_is_a_new_observation_that_supersedes_the_old_one(api_for, team):
    api = api_for(team.worker)
    a, other = make_asset(api), make_asset(api, label="Other")
    first = observe(api, a["id"], health_score=15, notes="typo, meant 51")["observation"]
    fix = observe(api, a["id"], health_score=51, supersedes_id=first["id"])["observation"]
    assert fix["supersedes_id"] == first["id"]
    assert api.get(f"/observations/{first['id']}").json()["health_score"] == 15  # the original is preserved
    bad = api.post("/observations", {"asset_id": other["id"], "health_score": 5, "supersedes_id": first["id"]})
    assert bad.status_code == 422  # cannot supersede an observation of a different asset


def test_roles_and_tenancy_for_observations(api_for, team):
    worker, viewer = api_for(team.worker), api_for(team.viewer)
    a = make_asset(worker)
    assert viewer.post("/observations", {"asset_id": a["id"], "health_score": 50}).status_code == 403
    oid = observe(worker, a["id"])["observation"]["id"]
    assert viewer.get(f"/observations/{oid}").status_code == 200
    outsider_ws = api_for(team.other_owner, team.other_ws)
    assert outsider_ws.get(f"/observations/{oid}").status_code == 404
    assert outsider_ws.post("/observations", {"asset_id": a["id"], "health_score": 50}).status_code == 404
    assert (
        worker.post(
            "/observations", {"asset_id": "00000000-0000-0000-0000-00000000beef", "health_score": 5}
        ).status_code
        == 404
    )
