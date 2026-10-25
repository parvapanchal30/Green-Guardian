"""Harvest records and the Yield KPI (ADR-056): validation, roles, tenancy, append-only corrections, totals per unit,
the dashboard figure, and the database guarantees."""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.modules.audit.models import AuditEvent
from tests.conftest import requires_pg_mode
from tests.helpers import ago, ahead, make_asset

pg = requires_pg_mode


def harvests(api, asset_id: str) -> dict:
    r = api.get(f"/assets/{asset_id}/harvests")
    assert r.status_code == 200, r.text
    return r.json()


def harvest(api, asset_id: str, quantity=120, unit="kg", **over):
    return api.post(f"/assets/{asset_id}/harvests", {"quantity": quantity, "unit": unit, **over})


def correct(api, asset_id: str, record_id: str, **over):
    body = {"quantity": 100, "unit": "kg", "note": "weighed again on the scale", **over}
    return api.post(f"/assets/{asset_id}/harvests/{record_id}/correct", body)


@pytest.fixture
def farm(api_for, team):
    """An agricultural workspace with a crop batch to harvest from."""
    owner = api_for(team.owner, team.agri_ws)
    return owner, make_asset(owner, label="Block A", kind="crop_batch", tracking_mode="population", estimated_count=100)


# ------------------------------------------------------------------ recording


def test_a_harvest_is_recorded_and_the_totals_follow(farm):
    owner, block = farm
    r = harvest(owner, block["id"], 120, "kg", grade="A", note="first picking", harvested_at=ago(days=2))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["totals"] == {"by_unit": {"kg": 120.0}, "mass_tonnes": 0.12, "records": 1}
    top = body["history"][0]
    assert (top["quantity"], top["unit"], top["grade"], top["note"]) == (120.0, "kg", "A", "first picking")
    assert top["effective"] is True and top["withdrawn"] is False and top["supersedes_id"] is None
    harvest(owner, block["id"], 0.5, "t")
    harvest(owner, block["id"], 40, "count")
    totals = harvests(owner, block["id"])["totals"]
    assert totals["by_unit"] == {"kg": 120.0, "t": 0.5, "count": 40.0}
    assert totals["mass_tonnes"] == 0.62  # kg and t are added as mass; counts are never converted into a weight
    assert totals["records"] == 3


def test_validation(farm):
    owner, block = farm
    for bad in (
        {"quantity": 0, "unit": "kg"},
        {"quantity": -5, "unit": "kg"},
        {"quantity": 5, "unit": "pounds"},
        {"quantity": 5},
        {"unit": "kg"},
        {"quantity": 1e12, "unit": "kg"},
        {"quantity": 5, "unit": "kg", "extra": 1},
        {"quantity": 5, "unit": "kg", "grade": "g" * 41},
        {"quantity": 5, "unit": "kg", "note": "n" * 1001},
    ):
        r = owner.post(f"/assets/{block['id']}/harvests", bad)
        assert r.status_code == 422, bad
    assert harvests(owner, block["id"])["history"] == []


def test_dates_cannot_be_in_the_future_or_before_planting(api_for, team):
    owner = api_for(team.owner, team.agri_ws)
    planted = make_asset(owner, label="Planted", planted_at="2026-01-10")
    r = harvest(owner, planted["id"], harvested_at=ahead(days=3))
    assert r.status_code == 422 and r.json()["code"] == "harvested_in_future"
    r = harvest(owner, planted["id"], harvested_at="2025-12-31T00:00:00+00:00")
    assert r.status_code == 422 and r.json()["code"] == "harvested_before_planting"
    assert harvest(owner, planted["id"], harvested_at="2026-01-10T12:00:00+00:00").status_code == 201


def test_an_asset_that_left_the_lifecycle_cannot_be_harvested(farm):
    owner, block = farm
    assert owner.post(f"/assets/{block['id']}/lifecycle", {"stage": "failed"}).status_code == 201
    r = harvest(owner, block["id"])
    assert r.status_code == 409 and r.json()["code"] == "asset_exited"


def test_roles(api_for, team, farm):
    owner, block = farm
    worker = api_for(team.worker)  # the green workspace: its own asset
    own = make_asset(worker)
    assert harvest(worker, own["id"]).status_code == 201
    assert harvest(api_for(team.viewer), own["id"]).status_code == 403
    rec = harvests(worker, own["id"])["history"][0]["id"]
    assert correct(worker, own["id"], rec).status_code == 403  # corrections are a manager's call
    assert harvests(api_for(team.viewer), own["id"])["totals"]["records"] == 1  # but a viewer can read


def test_tenants_are_isolated(api_for, team):
    mine = make_asset(api_for(team.worker))
    harvest(api_for(team.worker), mine["id"])
    rec = harvests(api_for(team.worker), mine["id"])["history"][0]["id"]
    theirs = api_for(team.other_owner, team.other_ws)
    assert theirs.get(f"/assets/{mine['id']}/harvests").status_code == 404
    assert harvest(theirs, mine["id"]).status_code == 404
    assert correct(theirs, mine["id"], rec).status_code == 404
    assert api_for(team.worker, team.other_ws).get(f"/assets/{mine['id']}/harvests").status_code == 404
    assert api_for(team.outsider).get(f"/assets/{mine['id']}/harvests").status_code == 404
    assert harvests(api_for(team.worker), mine["id"])["totals"]["records"] == 1


def test_a_record_of_another_asset_cannot_be_corrected_through_this_one(api_for, team):
    m = api_for(team.manager)
    a, b = make_asset(m, label="A"), make_asset(m, label="B")
    harvest(m, a["id"])
    rec_of_a = harvests(m, a["id"])["history"][0]["id"]
    assert correct(m, b["id"], rec_of_a).status_code == 404
    assert correct(m, a["id"], "00000000-0000-0000-0000-00000000dead").status_code == 404


# ------------------------------------------------------------------ corrections (append-only)


def test_a_correction_replaces_the_record_and_keeps_the_original(api_for, team):
    m = api_for(team.manager)
    a = make_asset(m)
    harvest(m, a["id"], 120)
    original = harvests(m, a["id"])["history"][0]
    r = correct(m, a["id"], original["id"], quantity=100, grade="B")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["totals"]["by_unit"] == {"kg": 100.0} and body["totals"]["records"] == 1
    fixed, old = body["history"][0], next(h for h in body["history"] if h["id"] == original["id"])
    assert len(body["history"]) == 2
    assert (
        fixed["supersedes_id"] == original["id"]
        and fixed["effective"]
        and fixed["note"] == "weighed again on the scale"
    )
    assert old["effective"] is False and old["superseded_by"] == fixed["id"] and old["quantity"] == 120.0


def test_a_correction_can_withdraw_a_record_and_can_change_the_unit_and_date(api_for, team):
    m = api_for(team.manager)
    a = make_asset(m)
    harvest(m, a["id"], 120, "kg")
    rec = harvests(m, a["id"])["history"][0]["id"]
    r = correct(m, a["id"], rec, quantity=0, note="entered against the wrong block")
    assert r.status_code == 201
    body = r.json()
    assert body["totals"] == {"by_unit": {}, "mass_tonnes": 0.0, "records": 0}
    assert body["history"][0]["withdrawn"] is True
    harvest(m, a["id"], 3, "kg")
    again = harvests(m, a["id"])["history"][0]["id"]
    r = correct(m, a["id"], again, quantity=3, unit="t", harvested_at=ago(days=1), note="it was tonnes, not kilograms")
    assert r.json()["totals"]["by_unit"] == {"t": 3.0}


def test_a_record_can_be_corrected_only_once_then_its_replacement_is_corrected(api_for, team):
    m = api_for(team.manager)
    a = make_asset(m)
    harvest(m, a["id"], 120)
    rec = harvests(m, a["id"])["history"][0]["id"]
    first = correct(m, a["id"], rec, quantity=110).json()["history"][0]["id"]
    again = correct(m, a["id"], rec, quantity=105)
    assert again.status_code == 409 and again.json()["code"] == "harvest_already_corrected"
    assert correct(m, a["id"], first, quantity=105).status_code == 201  # the latest version can be corrected
    assert harvests(m, a["id"])["totals"]["by_unit"] == {"kg": 105.0}


def test_a_correction_needs_a_reason(api_for, team):
    m = api_for(team.manager)
    a = make_asset(m)
    harvest(m, a["id"])
    rec = harvests(m, a["id"])["history"][0]["id"]
    for note in ("short", "", "         "):
        assert correct(m, a["id"], rec, note=note).status_code == 422, note
    assert m.post(f"/assets/{a['id']}/harvests/{rec}/correct", {"quantity": 1, "unit": "kg"}).status_code == 422


def test_every_change_is_audited(api_for, team, world):
    m = api_for(team.manager)
    a = make_asset(m)
    harvest(m, a["id"], 7, "kg")
    rec = harvests(m, a["id"])["history"][0]["id"]
    correct(m, a["id"], rec)
    with world.db() as db:
        actions = sorted(db.scalars(select(AuditEvent.action).where(AuditEvent.action.like("harvest.%"))).all())
    assert actions == ["harvest.correct", "harvest.record"]


def test_harvests_appear_in_the_asset_timeline(api_for, team):
    m = api_for(team.manager)
    a = make_asset(m)
    harvest(m, a["id"], 12.5, "kg", grade="A", note="first picking")
    rec = harvests(m, a["id"])["history"][0]["id"]
    correct(m, a["id"], rec, quantity=12)
    titles = [e["title"] for e in m.get(f"/assets/{a['id']}/timeline").json() if e["type"] == "harvest"]
    assert titles == ["Harvest correction: 12 kg", "Harvest: 12.5 kg"]


# ------------------------------------------------------------------ the Yield KPI


def yield_kpi(api) -> dict:
    return next(k for k in api.get("/dashboard").json()["kpis"] if k["key"] == "yield")


def test_the_yield_kpi_is_unavailable_until_something_is_harvested(farm):
    owner, _ = farm
    k = yield_kpi(owner)
    assert k["available"] is False and "No harvests recorded in the last 12 months" in k["reason"]


def test_the_yield_kpi_sums_effective_mass_over_twelve_months_and_names_what_it_leaves_out(farm):
    owner, block = farm
    other = make_asset(owner, label="Block B", kind="crop_batch", tracking_mode="population", estimated_count=50)
    harvest(owner, block["id"], 800, "kg", harvested_at=ago(days=30))
    harvest(owner, other["id"], 1.2, "t", harvested_at=ago(days=10))
    harvest(owner, block["id"], 30, "count")
    harvest(owner, block["id"], 5000, "kg", harvested_at=ago(days=400))  # outside the window
    k = yield_kpi(owner)
    assert k["available"] is True and k["unit"] == "t" and k["value"] == 2.0  # 0.8 + 1.2
    assert "2 recorded harvests from 2 assets in the last 12 months" in k["basis"]
    assert "not per area" in k["basis"] and "30 count" in k["basis"]


def test_a_correction_changes_the_kpi_and_a_withdrawn_record_leaves_it(farm):
    owner, block = farm
    harvest(owner, block["id"], 1000, "kg")
    rec = harvests(owner, block["id"])["history"][0]["id"]
    assert yield_kpi(owner)["value"] == 1.0
    correct(owner, block["id"], rec, quantity=400)
    assert yield_kpi(owner)["value"] == 0.4
    again = harvests(owner, block["id"])["history"][0]["id"]
    correct(owner, block["id"], again, quantity=0, note="duplicate of another entry")
    assert yield_kpi(owner)["available"] is False


def test_produce_harvested_before_the_asset_left_the_lifecycle_still_counts(farm):
    owner, block = farm
    harvest(owner, block["id"], 500, "kg")
    owner.post(f"/assets/{block['id']}/lifecycle", {"stage": "removed"})
    assert yield_kpi(owner)["value"] == 0.5


def test_only_counts_or_litres_cannot_be_turned_into_a_weight(farm):
    owner, block = farm
    harvest(owner, block["id"], 40, "count")
    k = yield_kpi(owner)
    assert k["available"] is False and "cannot be added to a weight" in k["reason"]


def test_the_green_workspace_has_no_yield_kpi_and_other_tenants_harvests_are_not_counted(api_for, team, farm):
    owner, block = farm
    harvest(owner, block["id"], 900, "kg")
    green = api_for(team.manager).get("/dashboard").json()
    assert "yield" not in [k["key"] for k in green["kpis"]]
    theirs = api_for(team.other_owner, team.other_ws)
    assert all(k["key"] != "yield" for k in theirs.get("/dashboard").json()["kpis"])


# ------------------------------------------------------------------ database guarantees (PostgreSQL only)


@pg
def test_harvest_records_are_append_only_and_constrained_in_the_database(api_for, team, world):
    m = api_for(team.manager)
    a = make_asset(m)
    harvest(m, a["id"], 5, "kg")
    base = "INSERT INTO harvest_records (id, workspace_id, asset_id, harvested_at, quantity, unit, note, supersedes_id, created_at) "
    cases = [
        (f"{base}VALUES (gen_random_uuid(), :ws, :a, now(), 5, 'stone', NULL, NULL, now())", "ck_harvest_records_unit"),
        (
            f"{base}VALUES (gen_random_uuid(), :ws, :a, now(), -1, 'kg', NULL, NULL, now())",
            "new_record_positive",
        ),  # a new record must be positive
        (f"{base}VALUES (gen_random_uuid(), :ws, :a, now(), 0, 'kg', NULL, NULL, now())", "new_record_positive"),
    ]
    with world.db() as db:
        for statement, constraint in cases:
            with pytest.raises(IntegrityError, match=constraint):
                db.execute(text(statement), {"ws": team.ws, "a": a["id"]})
            db.rollback()
        existing = db.execute(text("SELECT id FROM harvest_records WHERE asset_id = :a"), {"a": a["id"]}).scalar()
        negative_correction = (
            f"{base}VALUES (gen_random_uuid(), :ws, :a, now(), -1, 'kg', 'a written reason', '{existing}', now())"
        )
        with pytest.raises(IntegrityError, match="quantity_nonnegative"):  # even a correction cannot go below zero
            db.execute(text(negative_correction), {"ws": team.ws, "a": a["id"]})
        db.rollback()
        with pytest.raises(IntegrityError, match="fk_harvest_records_asset"):  # another tenant's workspace id
            db.execute(text(cases[0][0].replace("'stone'", "'kg'")), {"ws": team.other_ws, "a": a["id"]})
        db.rollback()
        for statement in (
            "UPDATE harvest_records SET quantity = 999 WHERE asset_id = :a",
            "DELETE FROM harvest_records WHERE asset_id = :a",
        ):
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(statement), {"a": a["id"]})
            db.rollback()


@pg
def test_the_database_allows_one_correction_per_record(api_for, team, world):
    m = api_for(team.manager)
    a = make_asset(m)
    harvest(m, a["id"], 5, "kg")
    rec = harvests(m, a["id"])["history"][0]["id"]
    correct(m, a["id"], rec, quantity=4)
    sql = (
        "INSERT INTO harvest_records (id, workspace_id, asset_id, harvested_at, quantity, unit, note, supersedes_id, created_at) "
        "VALUES (gen_random_uuid(), :ws, :a, now(), 3, 'kg', 'a second correction', :s, now())"
    )
    with world.db() as db, pytest.raises(IntegrityError, match="uq_harvest_records_supersedes"):
        db.execute(text(sql), {"ws": team.ws, "a": a["id"], "s": rec})


# ------------------------------------------------------------------ workspace overview (Harvests page)


def overview(api, **params) -> dict:
    r = api.get("/harvests", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_overview_adds_up_every_asset_by_unit_month_and_asset(api_for, team):
    owner = api_for(team.owner, team.agri_ws)
    a = make_asset(owner, label="Block A", kind="crop_batch", tracking_mode="population", estimated_count=10)
    b = make_asset(owner, label="Block B", kind="crop_batch", tracking_mode="population", estimated_count=10)
    harvest(owner, a["id"], 100, "kg", harvested_at=ago(days=40))
    harvest(owner, a["id"], 0.2, "t", harvested_at=ago(days=5))
    harvest(owner, b["id"], 30, "count", harvested_at=ago(days=5))
    harvest(owner, b["id"], 999, "kg", harvested_at=ago(days=3))
    mistake = [h for h in harvests(owner, b["id"])["history"] if h["quantity"] == 999][0]["id"]
    correct(owner, b["id"], mistake, quantity=0, note="this was entered twice by mistake")  # withdrawn
    body = overview(owner)
    assert body["totals"]["by_unit"] == {"kg": 100.0, "t": 0.2, "count": 30.0}
    assert body["totals"]["mass_tonnes"] == 0.3 and body["totals"]["records"] == 3  # the withdrawn record is gone
    assert [(r["asset_label"], r["unit"]) for r in body["records"]] == [
        ("Block B", "count"),
        ("Block A", "t"),
        ("Block A", "kg"),
    ]
    assert {m["month"] for m in body["by_month"]} <= {ago(days=40)[:7], ago(days=5)[:7]}
    first = body["by_asset"][0]
    assert (first["asset_label"], first["mass_tonnes"]) == ("Block A", 0.3)  # heaviest first
    assert overview(owner, asset_id=b["id"])["totals"]["by_unit"] == {"count": 30.0}


def test_the_overview_period(api_for, team):
    owner = api_for(team.owner, team.agri_ws)
    a = make_asset(owner, label="Block C", kind="crop_batch", tracking_mode="population", estimated_count=10)
    harvest(owner, a["id"], 50, "kg", harvested_at=ago(days=400))  # older than the default 12 months
    assert overview(owner)["totals"]["records"] == 0
    assert overview(owner, since=ago(days=500))["totals"]["records"] == 1
    r = owner.get("/harvests", params={"since": ago(days=1), "until": ago(days=2)})
    assert r.status_code == 422 and r.json()["code"] == "bad_period"
    r = owner.get("/harvests", params={"since": ago(days=1200)})
    assert r.status_code == 422 and r.json()["code"] == "period_too_long"


def test_the_overview_is_per_workspace(api_for, team):
    owner = api_for(team.owner, team.agri_ws)
    a = make_asset(owner, label="Block D", kind="crop_batch", tracking_mode="population", estimated_count=10)
    harvest(owner, a["id"], 10, "kg")
    assert overview(api_for(team.manager))["totals"]["records"] == 0  # the campus workspace has no harvests
