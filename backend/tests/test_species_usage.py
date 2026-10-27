"""Species with their use in this workspace (Species and Crops pages) and the asset list filtered by species."""

from __future__ import annotations

from tests.helpers import make_asset, species_id


def by_name(api, **params) -> dict[str, dict]:
    r = api.get("/species", params={"limit": 200, **params})
    assert r.status_code == 200, r.text
    return {s["common_name"]: s for s in r.json()["items"]}


def test_usage_counts_live_assets_and_plants_of_this_workspace_only(api_for, team):
    m = api_for(team.manager)
    other = api_for(team.other_owner, team.other_ws)
    neem = species_id(m, "Neem")
    make_asset(m, label="Neem A", species_id=neem)
    make_asset(m, label="Neem B", species_id=neem)
    dead = make_asset(m, label="Neem C", species_id=neem)
    assert m.post(f"/assets/{dead['id']}/lifecycle", {"stage": "dead", "note": "storm damage"}).status_code == 201
    gone = make_asset(m, label="Neem D", species_id=neem)
    assert m.delete(f"/assets/{gone['id']}").status_code in (200, 204)
    make_asset(other, label="Their neem", species_id=species_id(other, "Neem"))  # another tenant: never counted here

    s = by_name(m)["Neem"]
    assert (s["assets"], s["plants"]) == (2, None)  # the dead and the archived tree are not "in use"
    assert by_name(m)["Mango"]["assets"] == 0


def test_plants_add_up_the_estimated_counts_of_batches(api_for, team):
    owner = api_for(team.owner, team.agri_ws)
    tomato = species_id(owner, "Tomato")
    for label, n in (("Block A", 1200), ("Block B", 800)):
        make_asset(
            owner, label=label, kind="crop_batch", tracking_mode="population", estimated_count=n, species_id=tomato
        )
    s = by_name(owner, category="crop")["Tomato"]
    assert (s["assets"], s["plants"]) == (2, 2000)


def test_in_use_filter(api_for, team):
    m = api_for(team.manager)
    make_asset(m, label="Mango 1", species_id=species_id(m, "Mango"))
    used = by_name(m, in_use=True)
    assert list(used) == ["Mango"]
    assert "Mango" not in by_name(m, in_use=False)


def test_the_asset_list_filters_by_species(api_for, team):
    m = api_for(team.manager)
    neem, mango = species_id(m, "Neem"), species_id(m, "Mango")
    make_asset(m, label="N1", species_id=neem)
    make_asset(m, label="M1", species_id=mango)
    labels = [a["label"] for a in m.get("/assets", params={"species_id": neem}).json()["items"]]
    assert labels == ["N1"]


def test_mine_is_this_workspaces_species_only(api_for, team):
    """ADR-078: the Species page lists what this workspace uses or added, not the whole shared catalog."""
    m = api_for(team.manager)
    other = api_for(team.other_owner, team.other_ws)
    make_asset(m, label="Mango 1", species_id=species_id(m, "Mango"))
    assert m.post("/species", {"category": "tree", "common_name": "Jamun"}).status_code == 201
    assert other.post("/species", {"category": "tree", "common_name": "Kadamba"}).status_code == 201
    make_asset(other, label="Their neem", species_id=species_id(other, "Neem"))

    mine = by_name(m, mine=True)
    assert set(mine) == {"Mango", "Jamun"}  # used here, or added here
    assert "Kadamba" not in by_name(m)  # another workspace's own species is never visible
    assert {"Neem", "Mango", "Jamun"} <= set(by_name(m))  # the whole catalog is still there to choose from
    assert set(by_name(other, mine=True)) == {"Kadamba", "Neem"}
