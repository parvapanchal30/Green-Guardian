"""Operational map read model: spatial retrieval, server-side filters, isolation, layer registry."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.conftest import requires_pg_mode
from tests.helpers import make_asset, make_issue, make_location, make_task, observe

# Mumbai-ish points, a few hundred metres apart; FAR is in another country.
NEAR = {"latitude": 19.0760, "longitude": 72.8777}
NEAR2 = {"latitude": 19.0790, "longitude": 72.8800}
FAR = {"latitude": 28.6139, "longitude": 77.2090}


def feats(api, layer="assets", **params):
    r = api.get(f"/map/layers/{layer}", params=params or None)
    assert r.status_code == 200, r.text
    return r.json()


def ids(fc):
    return {f["properties"]["label"] for f in fc["features"]}


@pytest.fixture
def scene(api_for, team):
    """healthy@zone1, at_risk@zone1 (open task), critical@zone2 (open issue), unobserved@zone2, no coordinates."""
    w, m = api_for(team.worker), api_for(team.manager)
    z1 = make_location(m, "Zone 1", latitude=19.07, longitude=72.87)["id"]
    z2 = make_location(m, "Zone 2", latitude=28.6, longitude=77.2)["id"]
    a = make_asset(w, label="healthy", location_id=z1, **NEAR)
    b = make_asset(w, label="at_risk", location_id=z1, **NEAR2)
    c = make_asset(w, label="critical", kind="crop_batch", location_id=z2, **FAR)
    make_asset(w, label="unobserved", location_id=z2)  # no own coordinates -> drawn at its location
    make_asset(w, label="nowhere")  # no coordinates and no location
    observe(w, a["id"], health_score=90)
    observe(w, b["id"], health_score=55)
    observe(w, c["id"], health_score=20)
    make_issue(w, c["id"])
    make_task(m, asset_id=b["id"])
    return dict(z1=z1, z2=z2, a=a, b=b, c=c)


def test_returns_geojson_points_from_the_database(api_for, team, scene):
    fc = feats(api_for(team.viewer))
    assert fc["type"] == "FeatureCollection" and fc["layer"] == "assets" and not fc["truncated"]
    by = {f["properties"]["label"]: f for f in fc["features"]}
    assert set(by) == {"healthy", "at_risk", "critical", "unobserved"}  # "nowhere" cannot be drawn
    f = by["healthy"]
    assert f["geometry"] == {"type": "Point", "coordinates": [NEAR["longitude"], NEAR["latitude"]]}  # lon, lat order
    p = f["properties"]
    assert p["asset_id"] == scene["a"]["id"] == f["id"]
    assert (p["kind"], p["location_name"], p["health_band"], p["position_source"]) == (
        "tree",
        "Zone 1",
        "healthy",
        "asset",
    )
    assert (
        by["critical"]["properties"]["kind"] == "crop_batch" and by["critical"]["properties"]["open_issue_count"] == 1
    )
    assert by["at_risk"]["properties"]["open_task_count"] == 1
    assert fc["bbox"] == [72.8777, 19.076, 77.209, 28.6139]


def test_asset_without_coordinates_uses_its_location_centre(api_for, team, scene):
    by = {f["properties"]["label"]: f for f in feats(api_for(team.worker))["features"]}
    u = by["unobserved"]
    assert u["properties"]["position_source"] == "location" and u["properties"]["health_band"] is None
    assert u["geometry"]["coordinates"] == [77.2, 28.6]


def test_counts_cover_every_chip_and_the_undrawable(api_for, team, scene):
    c = feats(api_for(team.worker), filter="critical")["counts"]  # counts ignore the chip itself
    assert c == {"all": 4, "healthy": 1, "at_risk": 1, "critical": 1, "open_issues": 1, "tasks": 1, "unlocated": 1}


@pytest.mark.parametrize(
    "chip,expected",
    [
        ("all", {"healthy", "at_risk", "critical", "unobserved"}),
        ("healthy", {"healthy"}),
        ("at_risk", {"at_risk"}),
        ("critical", {"critical"}),
        ("open_issues", {"critical"}),
        ("tasks", {"at_risk"}),
    ],
)
def test_chip_filters_are_applied_server_side(api_for, team, scene, chip, expected):
    assert ids(feats(api_for(team.worker), filter=chip)) == expected


def test_location_and_kind_scope(api_for, team, scene):
    api = api_for(team.worker)
    assert ids(feats(api, location_id=scene["z1"])) == {"healthy", "at_risk"}
    assert ids(feats(api, kind="crop_batch")) == {"critical"}
    assert ids(feats(api, location_id=scene["z1"], kind="crop_batch")) == set()
    z1_counts = feats(api, location_id=scene["z1"])["counts"]
    assert z1_counts["all"] == 2 and z1_counts["critical"] == 0 and z1_counts["unlocated"] == 0


def test_bbox_clips_to_the_viewport(api_for, team, scene):
    api = api_for(team.worker)
    mumbai = feats(api, bbox="72.7,18.9,73.0,19.3")
    assert ids(mumbai) == {"healthy", "at_risk"}
    assert mumbai["counts"]["all"] == 4  # chip counts describe the scope, not the viewport
    assert ids(feats(api, bbox="77.0,28.4,77.4,28.8")) == {"critical", "unobserved"}  # incl. location-positioned asset
    assert feats(api, bbox="0,0,1,1")["features"] == []
    assert mumbai["bbox"][0] >= 72.7 and mumbai["bbox"][2] <= 73.0


@pytest.mark.parametrize("bbox", ["1,2,3", "a,b,c,d", "10,0,5,1", "0,50,1,40", "-200,0,0,1", "0,0,1,95"])
def test_invalid_bbox_is_a_422(api_for, team, bbox):
    r = api_for(team.worker).get("/map/layers/assets", params={"bbox": bbox})
    assert r.status_code == 422, r.text


def test_invalid_filter_and_limit_are_rejected(api_for, team):
    api = api_for(team.worker)
    assert api.get("/map/layers/assets", params={"filter": "yield"}).status_code == 422
    assert api.get("/map/layers/assets", params={"limit": 0}).status_code == 422


def test_limit_truncates_and_says_so(api_for, team, scene):
    fc = feats(api_for(team.worker), limit=2)
    assert len(fc["features"]) == 2 and fc["truncated"] is True
    assert feats(api_for(team.worker), limit=4)["truncated"] is False


def test_archived_assets_are_not_drawn(api_for, team, scene):
    assert api_for(team.manager).delete(f"/assets/{scene['a']['id']}").status_code < 300
    assert "healthy" not in ids(feats(api_for(team.worker)))


def test_empty_workspace_gives_an_empty_valid_collection(api_for, team):
    fc = feats(api_for(team.worker))
    assert fc["features"] == [] and fc["bbox"] is None and fc["truncated"] is False
    assert fc["counts"] == {
        "all": 0,
        "healthy": 0,
        "at_risk": 0,
        "critical": 0,
        "open_issues": 0,
        "tasks": 0,
        "unlocated": 0,
    }


def test_state_changes_show_on_the_map(api_for, team, scene):
    w = api_for(team.worker)
    observe(w, scene["a"]["id"], health_score=15)  # healthy -> critical
    assert ids(feats(w, filter="critical")) == {"healthy", "critical"}  # the label stays; the band moved
    assert ids(feats(w, filter="healthy")) == set()


def test_tenants_never_see_each_others_assets(api_for, team, scene):
    other = api_for(team.other_owner, team.other_ws)
    make_asset(other, label="theirs", **NEAR)
    assert ids(feats(other)) == {"theirs"}
    assert "theirs" not in ids(feats(api_for(team.worker)))
    # a location id from another tenant matches nothing and reveals nothing
    assert feats(other, location_id=scene["z1"])["features"] == []


def test_non_members_and_unknown_workspaces_get_404(api_for, team):
    assert api_for(team.outsider).get("/map/layers/assets").status_code == 404
    unknown = api_for(team.worker, "00000000-0000-0000-0000-000000000000")
    assert unknown.get("/map/layers/assets").status_code == 404
    assert unknown.get("/map/layers").status_code == 404


def test_both_modes_use_the_same_endpoint_and_shape(api_for, team):
    agri = api_for(team.owner, team.agri_ws)
    make_asset(agri, label="Batch 7", kind="crop_batch", **NEAR)
    fc = feats(agri)
    assert ids(fc) == {"Batch 7"} and fc["features"][0]["properties"]["kind"] == "crop_batch"


def test_layer_registry_declares_future_layers_without_serving_them(api_for, team):
    api = api_for(team.viewer)
    layers = {entry["key"]: entry for entry in api.get("/map/layers").json()}
    assert layers["assets"]["available"] is True
    future = {"disease_hotspots", "soil_moisture", "irrigation", "growth", "canopy", "survival_risk", "yield"}
    assert future <= set(layers) and all(layers[k]["available"] is False and layers[k]["requires"] for k in future)
    for k in future:
        r = api.get(f"/map/layers/{k}")
        assert r.status_code == 501 and r.json()["code"] == "capability_unavailable"
    assert api.get("/map/layers/nonsense").status_code == 404


@requires_pg_mode
def test_viewport_query_is_served_by_the_postgis_gist_indexes(world):
    """The map's bbox predicate must be index-assisted on PostgreSQL (ST_Intersects over the generated centroid)."""
    with world.db() as db:
        db.execute(text("SET LOCAL enable_seqscan = off"))
        for table in ("biological_assets", "locations"):
            plan = " ".join(
                r[0]
                for r in db.execute(
                    text(
                        f"EXPLAIN SELECT id FROM {table} WHERE ST_Intersects(centroid, ST_MakeEnvelope(72.7, 18.9, 73.0, 19.3, 4326))"
                    )
                )
            )
            assert f"ix_{table}_centroid_gist" in plan, plan
