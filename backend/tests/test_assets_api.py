"""Register -> profile for trees and crop batches, with validation, tenancy and role boundaries."""

from __future__ import annotations

import pytest

from tests.helpers import make_asset, make_location, observe, species_id


def test_register_a_tree_with_species_zone_and_metadata(api_for, team):
    api = api_for(team.worker)  # field staff may register assets
    zone = make_location(api_for(team.manager), "Ward 42 Zone 4", "zone", latitude=19.2, longitude=72.97)
    tree = make_asset(
        api,
        label="Neem #482",
        tag_code="WD42-0482",
        species_id=species_id(api, "Neem"),
        location_id=zone["id"],
        latitude=19.2012,
        longitude=72.9701,
        planted_at="2024-07-15",
        attributes={"girth_cm": 31, "guard": True},
        notes="Planted during the monsoon drive",
    )
    assert tree["kind"] == "tree" and tree["tracking_mode"] == "individual"
    assert tree["species_name"] == "Neem" and tree["location_name"] == "Ward 42 Zone 4"
    assert tree["current_stage"] == "planted"
    # a registered asset starts with an explicit, honest "unknown" state: no health is invented
    st = tree["state"]
    assert st["health_score"] is None and st["health_band"] is None and st["last_observed_at"] is None
    assert st["open_issue_count"] == 0 and st["open_task_count"] == 0

    again = api.get(f"/assets/{tree['id']}")
    assert again.status_code == 200 and again.json()["attributes"] == {"girth_cm": 31, "guard": True}


def test_crop_batch_is_a_population_asset_in_the_same_model(api_for, team):
    api = api_for(team.owner, team.agri_ws)
    field = make_location(api, "Field 3", "field")
    batch = make_asset(
        api,
        label="Tomato Batch #17",
        kind="crop_batch",
        tracking_mode="population",
        estimated_count=84200,
        species_id=species_id(api, "Tomato"),
        location_id=field["id"],
    )
    assert batch["tracking_mode"] == "population" and batch["estimated_count"] == 84200
    assert batch["species_name"] == "Tomato"


@pytest.mark.parametrize(
    "payload,field",
    [
        ({"kind": "tree"}, "label"),
        ({"label": "x", "kind": "spaceship"}, "kind"),
        ({"label": "x", "kind": "tree", "latitude": 95, "longitude": 0}, "latitude"),
        ({"label": "x", "kind": "tree", "latitude": 10}, None),  # lat without lon
        ({"label": "x", "kind": "crop_batch", "tracking_mode": "population"}, None),  # population needs a count
        ({"label": "x", "kind": "tree", "estimated_count": 5}, None),  # count only for population
        ({"label": "x", "kind": "tree", "mystery_field": 1}, None),  # unknown fields are rejected
        ({"label": "x", "kind": "tree", "attributes": {"blob": "z" * 20000}}, None),  # oversized JSON
        ({"label": "", "kind": "tree"}, "label"),
    ],
)
def test_asset_validation_errors_are_422_problem_details(api_for, team, payload, field):
    r = api_for(team.worker).post("/assets", payload)
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "validation_error" and r.headers["content-type"].startswith("application/problem+json")
    if field:
        assert any(e["loc"][-1] == field for e in r.json()["errors"])


def test_missing_and_foreign_resources_are_404_not_leaks(api_for, team):
    mine, theirs = api_for(team.worker), api_for(team.other_owner, team.other_ws)
    foreign_zone = make_location(theirs, "Their zone")
    foreign_asset = make_asset(theirs, label="Their tree")
    missing = "00000000-0000-0000-0000-00000000beef"

    assert mine.get(f"/assets/{missing}").json()["code"] == "asset_not_found"
    assert mine.get(f"/assets/{foreign_asset['id']}").status_code == 404  # another tenant's asset
    r = mine.post("/assets", {"label": "x", "kind": "tree", "location_id": missing})
    assert r.json()["code"] == "location_not_found"
    assert mine.post("/assets", {"label": "x", "kind": "tree", "location_id": foreign_zone["id"]}).status_code == 404
    assert (
        mine.post("/assets", {"label": "x", "kind": "tree", "species_id": missing}).json()["code"]
        == "species_not_found"
    )
    # and the other tenant's list never shows ours
    make_asset(mine, label="Our tree")
    assert {a["label"] for a in theirs.get("/assets").json()["items"]} == {"Their tree"}


def test_custom_species_are_private_to_their_workspace(api_for, team):
    mine, theirs = api_for(team.manager), api_for(team.other_owner, team.other_ws)
    r = mine.post("/species", {"category": "tree", "common_name": "Our Heritage Fig"})
    assert r.status_code == 201 and r.json()["is_global"] is False
    assert theirs.get("/species", params={"q": "heritage fig"}).json()["total"] == 0
    assert (
        mine.post("/species", {"category": "tree", "common_name": "our heritage FIG"}).json()["code"]
        == "species_exists"
    )
    assert (
        mine.post("/species", {"category": "tree", "common_name": "neem"}).json()["code"] == "species_exists"
    )  # global
    assert theirs.post("/assets", {"label": "x", "kind": "tree", "species_id": r.json()["id"]}).status_code == 404
    assert api_for(team.worker).post("/species", {"category": "tree", "common_name": "Nope"}).status_code == 403


def test_tag_codes_are_unique_per_workspace_only(api_for, team):
    mine, theirs = api_for(team.worker), api_for(team.other_owner, team.other_ws)
    make_asset(mine, label="A", tag_code="T-1")
    dup = mine.post("/assets", {"label": "B", "kind": "tree", "tag_code": "T-1"})
    assert dup.status_code == 409 and dup.json()["code"] == "tag_code_taken"
    assert theirs.post("/assets", {"label": "C", "kind": "tree", "tag_code": "T-1"}).status_code == 201  # other tenant


def test_roles_viewer_reads_worker_registers_manager_edits(api_for, team):
    viewer, worker, manager = api_for(team.viewer), api_for(team.worker), api_for(team.manager)
    assert viewer.post("/assets", {"label": "x", "kind": "tree"}).status_code == 403
    asset = make_asset(worker)
    assert viewer.get(f"/assets/{asset['id']}").status_code == 200
    assert worker.patch(f"/assets/{asset['id']}", {"label": "renamed"}).status_code == 403
    assert worker.delete(f"/assets/{asset['id']}").status_code == 403
    r = manager.patch(f"/assets/{asset['id']}", {"label": "Neem #1 (renamed)", "notes": "moved"})
    assert r.status_code == 200 and r.json()["label"] == "Neem #1 (renamed)"


def test_update_can_clear_and_set_relations_and_validates_them(api_for, team):
    mgr = api_for(team.manager)
    zone = make_location(mgr, "Z")
    asset = make_asset(mgr, location_id=zone["id"], species_id=species_id(mgr))
    cleared = mgr.patch(f"/assets/{asset['id']}", {"location_id": None}).json()
    assert cleared["location_id"] is None and cleared["species_id"] == asset["species_id"]
    assert mgr.patch(f"/assets/{asset['id']}", {"estimated_count": 5}).json()["code"] == "not_population_asset"
    assert mgr.patch(f"/assets/{asset['id']}", {"latitude": 10}).json()["code"] == "coords_pair"


def test_list_filters_search_and_pagination(api_for, team):
    mgr = api_for(team.manager)
    z1, z2 = make_location(mgr, "North"), make_location(mgr, "South")
    a = make_asset(mgr, label="Mango A", location_id=z1["id"])
    make_asset(mgr, label="Mango B", location_id=z2["id"])
    make_asset(mgr, label="Banyan", kind="tree", location_id=z2["id"])
    observe(mgr, a["id"], health_score=30)  # critical
    r = mgr.get("/assets", params={"q": "mango"}).json()
    assert r["total"] == 2 and {i["label"] for i in r["items"]} == {"Mango A", "Mango B"}
    assert mgr.get("/assets", params={"location_id": z2["id"]}).json()["total"] == 2
    assert [i["label"] for i in mgr.get("/assets", params={"health_band": "critical"}).json()["items"]] == ["Mango A"]
    page = mgr.get("/assets", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 1 and page["limit"] == 2
    assert mgr.get("/assets", params={"limit": 0}).status_code == 422
    assert mgr.get("/assets", params={"limit": 500}).status_code == 422


def test_archive_is_a_soft_delete_that_keeps_history(api_for, team):
    mgr = api_for(team.manager)
    a = make_asset(mgr)
    observe(mgr, a["id"])
    assert mgr.delete(f"/assets/{a['id']}").status_code == 204
    assert mgr.get(f"/assets/{a['id']}").status_code == 404
    assert mgr.get("/assets").json()["total"] == 0
    kinds = sorted(e["type"] for e in mgr.get(f"/assets/{a['id']}/timeline").json())
    assert kinds == ["lifecycle", "observation"]  # history (the initial stage and the observation) is still readable
    assert mgr.post("/observations", {"asset_id": a["id"], "health_score": 50}).status_code == 404  # but no new data


def test_locations_hierarchy_and_validation(api_for, team):
    mgr = api_for(team.manager)
    site = make_location(mgr, "Campus", "site")
    zone = make_location(mgr, "Block A", "zone", parent_id=site["id"])
    assert zone["parent_id"] == site["id"]
    assert mgr.post("/locations", {"name": "x", "kind": "zone", "latitude": 5}).status_code == 422
    assert mgr.post("/locations", {"name": "x", "kind": "galaxy"}).status_code == 422
    r = mgr.post("/locations", {"name": "x", "kind": "zone", "parent_id": "00000000-0000-0000-0000-00000000beef"})
    assert r.status_code == 404
    assert api_for(team.worker).post("/locations", {"name": "x", "kind": "zone"}).status_code == 403
    assert mgr.get("/locations", params={"kind": "site"}).json()["total"] == 1
