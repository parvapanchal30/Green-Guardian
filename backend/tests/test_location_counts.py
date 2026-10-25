"""Fields and zones list: living assets per location, those needing attention, active recurring inspections."""

from __future__ import annotations

from tests.helpers import make_asset, make_location, observe


def test_counts_per_location(api_for, team):
    m = api_for(team.manager)
    north, south = make_location(m, name="North"), make_location(m, name="South")
    ok = make_asset(m, label="Healthy", location_id=north["id"])
    sick = make_asset(m, label="Sick", location_id=north["id"])
    dead = make_asset(m, label="Dead", location_id=north["id"])
    observe(m, ok["id"], health_score=90)
    observe(m, sick["id"], health_score=20)
    assert m.post(f"/assets/{dead['id']}/lifecycle", {"stage": "dead", "note": "storm damage"}).status_code == 201
    assert m.post("/schedules", {"location_id": north["id"], "interval_days": 14}).status_code == 201
    paused = m.post("/schedules", {"location_id": south["id"], "interval_days": 7}).json()
    m.patch(f"/schedules/{paused['id']}", {"active": False})

    rows = {r["name"]: r for r in m.get("/locations").json()["items"]}
    assert (rows["North"]["assets"], rows["North"]["needs_attention"], rows["North"]["schedules"]) == (2, 1, 1)
    assert (rows["South"]["assets"], rows["South"]["needs_attention"], rows["South"]["schedules"]) == (0, 0, 0)
    # another tenant's locations and counts are never mixed in
    other = api_for(team.other_owner, team.other_ws)
    assert [r["name"] for r in other.get("/locations").json()["items"]] == []


def test_tasks_can_be_filtered_by_several_types(api_for, team):
    from tests.helpers import make_task

    m = api_for(team.manager)
    a = make_asset(m)
    for kind in ("inspect", "monitor", "water"):
        make_task(m, title=kind, type=kind, asset_id=a["id"])
    got = m.get("/tasks", params=[("type", "inspect"), ("type", "monitor"), ("asset_id", a["id"])]).json()["items"]
    assert sorted(t["type"] for t in got) == ["inspect", "monitor"]
    assert [t["type"] for t in m.get("/tasks", params={"type": "water", "asset_id": a["id"]}).json()["items"]] == [
        "water"
    ]
