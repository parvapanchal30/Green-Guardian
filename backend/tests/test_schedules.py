"""Recurring inspections (ADR-062): schedules, task generation (lead time, catching up, no piling up, inactive assets),
pausing, roles, tenancy, audit, and the database guarantees."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.modules.audit.models import AuditEvent
from app.modules.schedules import service
from tests.conftest import requires_pg_mode
from tests.helpers import ago, ahead, iso, make_asset, make_location

pg = requires_pg_mode


def at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def schedule(api, **over):
    return api.post("/schedules", {"interval_days": 7, **over})


def tasks_of(api, asset_id: str) -> list[dict]:
    return api.get("/tasks", params={"asset_id": asset_id, "limit": 100}).json()["items"]


def generate(world, now: datetime):
    with world.db() as db:
        return service.generate(db, now=now)


@pytest.fixture
def tree(api_for, team):
    m = api_for(team.manager)
    return m, make_asset(m, label="Neem #5")


# ------------------------------------------------------------------ creating


def test_a_schedule_due_now_creates_its_first_task_at_once(tree, team):
    m, a = tree
    r = schedule(m, asset_id=a["id"], assignee_id=str(team.worker.id), priority="p2")
    assert r.status_code == 201, r.text
    s = r.json()
    assert (s["title"], s["task_type"], s["interval_days"], s["active"], s["asset_label"]) == (
        "Inspect Neem #5",
        "inspect",
        7,
        True,
        "Neem #5",
    )
    [occ] = s["occurrences"]
    assert occ["outcome"] == "created" and occ["missed"] == 0 and occ["task_status"] == "todo"
    [task] = tasks_of(m, a["id"])
    assert (task["key"], task["type"], task["source"], task["priority"]) == (
        occ["task_key"],
        "inspect",
        "schedule",
        "p2",
    )
    assert task["assignee_id"] == str(team.worker.id) and task["title"] == "Inspect Neem #5"
    assert at(s["next_due_at"]) - at(occ["due_at"]) == timedelta(days=7)
    detail = m.get(f"/tasks/{task['id']}").json()
    assert detail["history"][0]["actor_id"] is None and "schedule" in detail["history"][0]["note"]


def test_validation_and_roles(api_for, team):
    m, w, v = api_for(team.manager), api_for(team.worker), api_for(team.viewer)
    a = make_asset(m)
    loc = make_location(m)
    assert schedule(m).status_code == 422  # no subject
    assert schedule(m, asset_id=a["id"], location_id=loc["id"]).status_code == 422  # two subjects
    assert schedule(m, asset_id=a["id"], interval_days=0).status_code == 422
    assert schedule(m, asset_id=a["id"], interval_days=366).status_code == 422
    assert schedule(m, asset_id=a["id"], interval_days=7, lead_days=7).status_code == 422  # lead must be shorter
    assert schedule(m, asset_id=a["id"], task_type="water").status_code == 422
    r = schedule(m, asset_id=a["id"], first_due_at=ago(days=400))
    assert r.status_code == 422 and r.json()["code"] == "due_too_old"
    r = schedule(m, asset_id=a["id"], assignee_id=str(team.outsider.id))
    assert r.status_code == 422 and r.json()["code"] == "assignee_not_member"
    r = schedule(m, asset_id="00000000-0000-0000-0000-00000000dead")
    assert r.status_code == 404 and r.json()["code"] == "asset_not_found"
    assert schedule(w, asset_id=a["id"]).status_code == 403  # a manager decides the routine
    assert v.get("/schedules").status_code == 200
    assert v.post("/schedules/generate").status_code == 403


def test_no_schedule_for_an_asset_that_left_the_lifecycle(tree):
    m, a = tree
    assert m.post(f"/assets/{a['id']}/lifecycle", {"stage": "dead", "note": "storm damage"}).status_code == 201
    r = schedule(m, asset_id=a["id"])
    assert r.status_code == 409 and r.json()["code"] == "asset_inactive"


def test_a_location_schedule_creates_one_task_for_the_location(api_for, team):
    m = api_for(team.manager)
    loc = make_location(m, name="North block")
    s = schedule(m, location_id=loc["id"], task_type="monitor", title="Walk the north block").json()
    assert s["location_name"] == "North block" and s["asset_id"] is None
    task = m.get(f"/tasks/{s['occurrences'][0]['task_id']}").json()
    assert (task["type"], task["location_id"], task["asset_id"], task["title"]) == (
        "monitor",
        loc["id"],
        None,
        "Walk the north block",
    )


# ------------------------------------------------------------------ generating


def test_lead_time_and_the_next_round(tree, world):
    m, a = tree
    due = datetime.now(UTC) + timedelta(days=5)
    s = schedule(m, asset_id=a["id"], first_due_at=iso(due), lead_days=2).json()
    assert s["occurrences"] == [] and tasks_of(m, a["id"]) == []
    assert generate(world, due - timedelta(days=2, minutes=1)).created == 0  # just before the lead window
    g = generate(world, due - timedelta(days=2))
    assert (g.due, g.created) == (1, 1)
    [task] = tasks_of(m, a["id"])
    assert at(task["due_at"]) == due  # the task is due on the schedule's date, created two days ahead
    assert generate(world, due).created == 0  # nothing new until the next round
    assert at(m.get(f"/schedules/{s['id']}").json()["next_due_at"]) == due + timedelta(days=7)


def test_an_open_task_is_not_piled_up_and_the_round_moves_on(tree, team, world, api_for):
    m, a = tree
    s = schedule(m, asset_id=a["id"], assignee_id=str(team.worker.id)).json()
    first = s["occurrences"][0]
    later = at(s["next_due_at"])
    g = generate(world, later)
    assert (g.created, g.skipped_open_task) == (0, 1)
    assert len(tasks_of(m, a["id"])) == 1
    w = api_for(team.worker)
    assert w.post(f"/tasks/{first['task_id']}/transitions", {"to_status": "done", "note": "looked"}).status_code == 200
    assert generate(world, later + timedelta(days=7)).created == 1
    outcomes = [o["outcome"] for o in m.get(f"/schedules/{s['id']}").json()["occurrences"]]
    assert outcomes == ["created", "skipped_open_task", "created"]  # newest first


def test_a_long_gap_creates_one_task_for_the_latest_date_and_counts_the_missed_ones(tree):
    m, a = tree
    # first due 20 days ago and never generated (no worker was running): one task for the latest date
    start = datetime.now(UTC) - timedelta(days=20)
    created = schedule(m, asset_id=a["id"], first_due_at=iso(start)).json()
    [occ] = created["occurrences"]
    assert occ["missed"] == 2 and at(occ["due_at"]) == start + timedelta(days=14)  # -20, -13 passed over; -6 created
    assert at(created["next_due_at"]) == start + timedelta(days=21)
    assert len(tasks_of(m, a["id"])) == 1


def test_a_schedule_stops_when_its_plant_dies(tree, world):
    m, a = tree
    s = schedule(m, asset_id=a["id"], first_due_at=ahead(days=3)).json()
    assert m.post(f"/assets/{a['id']}/lifecycle", {"stage": "dead", "note": "storm damage"}).status_code == 201
    g = generate(world, datetime.now(UTC) + timedelta(days=3))
    assert (g.due, g.skipped_inactive_asset, g.created) == (1, 1, 0)
    after = m.get(f"/schedules/{s['id']}").json()
    assert after["active"] is False and after["occurrences"][0]["outcome"] == "skipped_inactive_asset"
    r = m.patch(f"/schedules/{s['id']}", {"active": True})
    assert r.status_code == 409 and r.json()["code"] == "asset_inactive"


def test_pause_resume_and_edit(tree, team, world):
    m, a = tree
    s = schedule(m, asset_id=a["id"], first_due_at=ahead(days=1)).json()
    assert m.patch(f"/schedules/{s['id']}", {"active": False}).json()["active"] is False
    assert generate(world, datetime.now(UTC) + timedelta(days=2)).due == 0  # paused: nothing happens
    r = m.patch(f"/schedules/{s['id']}", {"active": True, "interval_days": 14, "title": "Check the crown"})
    body = r.json()
    assert (body["active"], body["interval_days"], body["title"], body["version"]) == (True, 14, "Check the crown", 3)
    assert m.patch(f"/schedules/{s['id']}", {"lead_days": 14}).json()["code"] == "lead_too_long"
    moved = m.patch(f"/schedules/{s['id']}", {"next_due_at": ago(minutes=1)}).json()  # moving it into the past: due now
    assert moved["occurrences"][0]["outcome"] == "created"
    assert m.patch(f"/schedules/{s['id']}", {"assignee_id": str(team.outsider.id)}).status_code == 422
    with world.db() as db:
        actions = db.scalars(select(AuditEvent.action).where(AuditEvent.target_type == "schedule")).all()
    assert {"schedule.create", "schedule.update", "schedule.generate"} <= set(actions)


def test_generating_twice_at_the_same_moment_creates_one_task(tree, world):
    m, a = tree
    due = datetime.now(UTC) + timedelta(days=2)
    schedule(m, asset_id=a["id"], first_due_at=iso(due))
    assert generate(world, due).created == 1
    assert generate(world, due).created == 0
    assert len(tasks_of(m, a["id"])) == 1


def test_the_generate_endpoint_is_scoped_to_its_workspace(api_for, team, world):
    m, other = api_for(team.manager), api_for(team.other_owner, team.other_ws)
    mine = make_asset(m)
    theirs = make_asset(other)
    for api, asset in ((m, mine), (other, theirs)):
        schedule(api, asset_id=asset["id"], first_due_at=ahead(minutes=30))  # due soon, not yet created
    with world.db() as db:  # make both due now
        db.execute(
            text("UPDATE inspection_schedules SET next_due_at = :t"), {"t": datetime.now(UTC) - timedelta(minutes=1)}
        )
        db.commit()
    r = m.post("/schedules/generate")
    assert r.status_code == 200 and r.json()["created"] == 1
    assert len(tasks_of(m, mine["id"])) == 1 and tasks_of(other, theirs["id"]) == []
    assert other.get("/schedules").json()[0]["asset_id"] == theirs["id"]
    assert len(m.get("/schedules").json()) == 1  # each tenant sees only its own


def test_another_tenants_schedule_is_not_found(api_for, team):
    m, other = api_for(team.manager), api_for(team.other_owner, team.other_ws)
    theirs = schedule(other, asset_id=make_asset(other)["id"]).json()
    assert m.get(f"/schedules/{theirs['id']}").status_code == 404
    assert m.patch(f"/schedules/{theirs['id']}", {"active": False}).status_code == 404


# ------------------------------------------------------------------ database guarantees (PostgreSQL)


@pg
def test_occurrences_are_append_only_and_unique_per_due_date(tree, team, world):
    m, a = tree
    s = schedule(m, asset_id=a["id"]).json()
    occ = s["occurrences"][0]
    with world.db() as db:
        with pytest.raises(IntegrityError, match="uq_schedule_occurrences_due"):
            db.execute(
                text(
                    "INSERT INTO schedule_occurrences (id, workspace_id, schedule_id, due_at, outcome, missed, created_at) "
                    "VALUES (gen_random_uuid(), :ws, :s, :d, 'skipped_open_task', 0, now())"
                ),
                {"ws": team.ws, "s": s["id"], "d": occ["due_at"]},
            )
        db.rollback()
        with pytest.raises(IntegrityError, match="task_when_created"):
            db.execute(
                text(
                    "INSERT INTO schedule_occurrences (id, workspace_id, schedule_id, due_at, outcome, missed, created_at) "
                    "VALUES (gen_random_uuid(), :ws, :s, now(), 'created', 0, now())"
                ),
                {"ws": team.ws, "s": s["id"]},
            )
        db.rollback()
        for statement in ("UPDATE schedule_occurrences SET missed = 9", "DELETE FROM schedule_occurrences"):
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(statement))
            db.rollback()
        with pytest.raises(IntegrityError, match="one_subject"):
            db.execute(text("UPDATE inspection_schedules SET asset_id = NULL WHERE id = :s"), {"s": s["id"]})
        db.rollback()
