"""Actions and verification (ADR-059): recording work, roles, links to issues and tasks, follow-up inspections,
append-only corrections, the verification rule, the follow-up requirement for closing a plant issue as fixed, the
timeline, and the database guarantees."""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.modules.audit.models import AuditEvent
from tests.conftest import requires_pg_mode
from tests.helpers import ago, ahead, make_asset, make_issue, make_location, make_task, observe

pg = requires_pg_mode


def act(api, asset_id: str, kind: str = "treat", **over):
    return api.post(f"/assets/{asset_id}/actions", {"kind": kind, **over})


def actions(api, asset_id: str) -> list[dict]:
    r = api.get(f"/assets/{asset_id}/actions")
    assert r.status_code == 200, r.text
    return r.json()["history"]


def correct(api, asset_id: str, action_id: str, **over):
    body = {"kind": "treat", "note": "recorded the wrong product", **over}
    return api.post(f"/assets/{asset_id}/actions/{action_id}/correct", body)


def close(api, issue_id: str, outcome: str = "fixed", state: str = "resolved", **resolution):
    return api.post(
        f"/issues/{issue_id}/transitions",
        {"to_state": state, "resolution": {"outcome": outcome, "notes": "done", **resolution}},
    )


def issue_detail(api, issue_id: str) -> dict:
    r = api.get(f"/issues/{issue_id}")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def sick(api_for, team):
    """A tree with a recorded health score of 30 and an open plant-health issue about it."""
    m, w = api_for(team.manager), api_for(team.worker)
    tree = make_asset(m, label="Neem #7", planted_at="2020-01-01")
    observe(w, tree["id"], health_score=30, observed_at=ago(hours=3))
    issue = make_issue(m, tree["id"], title="Leaf spot")
    return m, w, tree, issue


# ------------------------------------------------------------------ recording


def test_work_is_recorded_with_what_how_much_when_and_who(api_for, team, world):
    w = api_for(team.worker)
    tree = make_asset(w)
    r = act(
        w,
        tree["id"],
        "treat",
        product="Neem oil 1%",
        quantity=2,
        unit="l",
        note="whole canopy",
        performed_at=ago(hours=1),
    )
    assert r.status_code == 201, r.text
    [a] = r.json()["history"]
    assert (a["kind"], a["product"], a["quantity"], a["unit"], a["note"]) == (
        "treat",
        "Neem oil 1%",
        2.0,
        "l",
        "whole canopy",
    )
    assert a["performed_by"] == a["recorded_by"] == str(team.worker.id)
    assert a["effective"] is True and a["withdrawn"] is False and a["issue_id"] is None and a["task_id"] is None
    act(w, tree["id"], "water")
    assert [x["kind"] for x in actions(w, tree["id"])] == ["water", "treat"]  # newest first
    with world.db() as db:
        audited = db.scalars(select(AuditEvent.action).where(AuditEvent.target_type == "action")).all()
    assert audited.count("action.record") == 2


def test_validation(api_for, team):
    w = api_for(team.worker)
    tree = make_asset(w, planted_at="2024-06-01")
    assert act(w, tree["id"], "dig").status_code == 422  # not a kind of action
    assert act(w, tree["id"], quantity=2).status_code == 422  # a quantity needs a unit
    assert act(w, tree["id"], unit="l").status_code == 422  # and a unit a quantity
    assert act(w, tree["id"], quantity=0, unit="l").status_code == 422
    assert act(w, tree["id"], quantity=1, unit="bucket").status_code == 422
    assert act(w, tree["id"], follow_up_days=0).status_code == 422
    assert act(w, tree["id"], follow_up_days=91).status_code == 422
    r = act(w, tree["id"], performed_at=ahead(hours=1))
    assert r.status_code == 422 and r.json()["code"] == "performed_in_future"
    r = act(w, tree["id"], performed_at="2024-01-01T00:00:00Z")
    assert r.status_code == 422 and r.json()["code"] == "performed_before_planting"
    assert actions(w, tree["id"]) == []


def test_roles(api_for, team):
    m, w, v = api_for(team.manager), api_for(team.worker), api_for(team.viewer)
    tree = make_asset(m)
    assert act(v, tree["id"]).status_code == 403  # a viewer reads only
    assert v.get(f"/assets/{tree['id']}/actions").status_code == 200
    r = act(w, tree["id"], performed_by=str(team.manager.id))
    assert r.status_code == 403 and r.json()["code"] == "insufficient_role"  # a worker records their own work only
    r = act(m, tree["id"], performed_by=str(team.outsider.id))
    assert r.status_code == 422 and r.json()["code"] == "assignee_not_member"
    r = act(m, tree["id"], performed_by=str(team.worker.id))
    assert r.status_code == 201
    [a] = r.json()["history"]
    assert a["performed_by"] == str(team.worker.id) and a["recorded_by"] == str(team.manager.id)


def test_no_work_on_an_asset_that_left_the_lifecycle(api_for, team):
    m = api_for(team.manager)
    tree = make_asset(m)
    assert m.post(f"/assets/{tree['id']}/lifecycle", {"stage": "dead", "note": "storm damage"}).status_code == 201
    r = act(m, tree["id"])
    assert r.status_code == 409 and r.json()["code"] == "asset_exited"


def test_an_action_can_only_name_an_open_issue_of_the_same_asset(sick, api_for, team):
    m, w, tree, issue = sick
    other = make_asset(m, label="Other")
    r = act(w, other["id"], issue_id=issue["id"])
    assert r.status_code == 422 and r.json()["code"] == "issue_asset_mismatch"
    r = act(w, tree["id"], issue_id="00000000-0000-0000-0000-00000000dead")
    assert r.status_code == 404 and r.json()["code"] == "issue_not_found"
    assert act(w, tree["id"], issue_id=issue["id"]).status_code == 201
    observe(w, tree["id"], notes="looked")
    assert close(m, issue["id"]).status_code == 200
    r = act(w, tree["id"], issue_id=issue["id"])
    assert r.status_code == 409 and r.json()["code"] == "issue_closed"


def test_another_tenants_issue_is_not_found(api_for, team):
    m, other = api_for(team.manager), api_for(team.other_owner, team.other_ws)
    tree = make_asset(m)
    foreign_tree = make_asset(other)
    foreign_issue = make_issue(other, foreign_tree["id"])
    r = act(m, tree["id"], issue_id=foreign_issue["id"])
    assert r.status_code == 404 and r.json()["code"] == "issue_not_found"


# ------------------------------------------------------------------ follow-up inspection


def test_a_follow_up_inspection_is_scheduled_for_the_issue(sick, team):
    m, w, tree, issue = sick
    r = act(w, tree["id"], "pest_control", issue_id=issue["id"], product="Neem oil", follow_up_days=7)
    assert r.status_code == 201, r.text
    [a] = r.json()["history"]
    assert a["issue_key"] == issue["key"] and a["follow_up_task_key"]
    task = m.get(f"/tasks/{a['follow_up_task_id']}").json()
    assert task["type"] == "inspect" and task["status"] == "todo" and task["issue_id"] == issue["id"]
    assert task["asset_id"] == tree["id"] and task["assignee_id"] == str(team.worker.id)
    assert "pest control" in task["title"] and "Neem #7" in task["title"]
    assert ago(days=-6) < task["due_at"] < ago(days=-8)  # about seven days from now
    detail = issue_detail(m, issue["id"])
    assert [t["key"] for t in detail["tasks"]] == [a["follow_up_task_key"]]


def test_a_follow_up_without_an_issue_is_a_plain_inspection_task(api_for, team):
    w = api_for(team.worker)
    tree = make_asset(w)
    [a] = act(w, tree["id"], "fertilize", quantity=0.5, unit="kg", follow_up_days=14).json()["history"]
    task = w.get(f"/tasks/{a['follow_up_task_id']}").json()
    assert task["issue_id"] is None and task["source"] == "manual" and task["asset_id"] == tree["id"]


# ------------------------------------------------------------------ completing a task records what was done


def test_completing_a_task_records_the_action_on_its_asset_and_issue(sick, team):
    m, w, tree, issue = sick
    task = make_task(m, title="Spray", type="treat", issue_id=issue["id"], assignee_id=str(team.worker.id))
    body = {
        "to_status": "done",
        "note": "sprayed",
        "action": {"kind": "treat", "product": "Copper fungicide", "quantity": 1.5, "unit": "l"},
        "observation": {"health_score": 45, "notes": "spots drying"},
    }
    r = w.post(f"/tasks/{task['id']}/transitions", body)
    assert r.status_code == 200, r.text
    [a] = actions(m, tree["id"])
    assert (a["task_key"], a["issue_key"], a["product"], a["quantity"]) == (
        task["key"],
        issue["key"],
        "Copper fungicide",
        1.5,
    )
    v = issue_detail(m, issue["id"])["verification"]
    # the check recorded with the completion is the follow-up of the work recorded with it
    assert (v["status"], v["actions"], v["baseline_score"], v["follow_up_score"], v["change"]) == (
        "improved",
        1,
        30,
        45,
        15,
    )


def test_an_action_needs_a_completed_task_with_an_asset(api_for, team):
    m = api_for(team.manager)
    tree = make_asset(m)
    task = make_task(m, asset_id=tree["id"])
    r = m.post(f"/tasks/{task['id']}/transitions", {"to_status": "in_progress", "action": {"kind": "water"}})
    assert r.status_code == 422 and r.json()["code"] == "action_needs_done"
    loc = make_location(m)
    no_asset = make_task(m, location_id=loc["id"])
    r = m.post(f"/tasks/{no_asset['id']}/transitions", {"to_status": "done", "action": {"kind": "water"}})
    assert r.status_code == 422 and r.json()["code"] == "task_has_no_asset"


# ------------------------------------------------------------------ corrections


def test_a_manager_corrects_or_withdraws_a_record_once_with_a_reason(sick, api_for, team, world):
    m, w, tree, issue = sick
    [a] = act(w, tree["id"], issue_id=issue["id"], product="Neem oil").json()["history"]
    r = correct(w, tree["id"], a["id"])
    assert r.status_code == 403  # corrections are a manager's
    assert correct(m, tree["id"], a["id"], note="short").status_code == 422
    r = correct(m, tree["id"], a["id"], product="Copper fungicide")
    assert r.status_code == 201, r.text
    new, old = r.json()["history"]
    assert new["supersedes_id"] == old["id"] and old["superseded_by"] == new["id"]
    assert old["effective"] is False and new["effective"] is True
    assert new["issue_id"] == issue["id"] and new["performed_by"] == old["performed_by"]  # the links are kept
    assert new["performed_at"] == old["performed_at"]
    r = correct(m, tree["id"], a["id"])
    assert r.status_code == 409 and r.json()["code"] == "action_already_corrected"
    r = correct(m, tree["id"], new["id"], withdrawn=True, note="this work was never done")
    assert r.status_code == 201
    assert issue_detail(m, issue["id"])["verification"]["actions"] == 0  # a withdrawn record no longer counts
    with world.db() as db:
        audited = db.scalars(select(AuditEvent.action).where(AuditEvent.action == "action.correct")).all()
    assert len(audited) == 2
    r = correct(m, tree["id"], "00000000-0000-0000-0000-00000000dead")
    assert r.status_code == 404 and r.json()["code"] == "action_not_found"


def test_a_withdrawal_must_be_a_correction(api_for, team):
    m = api_for(team.manager)
    tree = make_asset(m)
    assert act(m, tree["id"], withdrawn=True).status_code == 422  # unknown field on a new record


# ------------------------------------------------------------------ verification


def test_closing_a_plant_issue_as_fixed_needs_a_look_after_the_work(sick):
    m, w, tree, issue = sick
    v = issue_detail(m, issue["id"])["verification"]
    assert (v["status"], v["method"], v["required_for_success"], v["baseline_score"]) == (
        "awaiting_follow_up",
        "rule",
        True,
        30,
    )
    for outcome in ("fixed", "mitigated"):
        r = close(m, issue["id"], outcome)
        assert r.status_code == 409 and r.json()["code"] == "follow_up_required", r.text
    act(w, tree["id"], issue_id=issue["id"], performed_at=ago(hours=2))
    observe(w, tree["id"], health_score=50, observed_at=ago(hours=2, minutes=30))  # before the work: not a follow-up
    assert close(m, issue["id"]).json()["code"] == "follow_up_required"
    r = close(m, issue["id"], follow_up={"health_score": 70, "notes": "new leaves"})
    assert r.status_code == 200, r.text
    body = r.json()
    v = body["verification"]
    # the baseline is the latest score before the work (50), not the score at the opening (30)
    assert (v["status"], v["baseline_score"], v["follow_up_score"], v["change"], v["actions"]) == (
        "improved",
        50,
        70,
        20,
        1,
    )
    assert any(e["notes"] == "new leaves" for e in body["evidence"])  # the follow-up is attached as evidence


def test_outcomes_that_claim_no_success_need_no_follow_up(sick):
    m, _, _, issue = sick
    assert close(m, issue["id"], "no_action_needed").status_code == 200
    r = m.post(f"/issues/{issue['id']}/transitions", {"to_state": "investigating", "note": "reopened"})
    assert r.status_code == 200
    r = close(m, issue["id"], "wont_fix", state="closed_wont_fix", notes="the tree is scheduled for removal")
    assert r.status_code == 200


def test_unchanged_worse_and_unscored_follow_ups_are_named_as_such(api_for, team):
    m, w = api_for(team.manager), api_for(team.worker)

    def scenario(follow_up: dict) -> dict:
        tree = make_asset(m)
        observe(w, tree["id"], health_score=60, observed_at=ago(hours=2))
        issue = make_issue(m, tree["id"])
        act(w, tree["id"], issue_id=issue["id"])
        observe(w, tree["id"], **follow_up)
        return issue_detail(m, issue["id"])["verification"]

    assert scenario({"health_score": 63})["status"] == "unchanged"  # within 5 points either way
    assert scenario({"health_score": 55})["status"] == "worse"
    v = scenario({"health_score": None, "notes": "still spotted"})
    assert v["status"] == "observed_without_score" and v["follow_up_score"] is None and v["follow_up_at"]
    tree = make_asset(m)  # no score before the work either
    issue = make_issue(m, tree["id"])
    observe(w, tree["id"], health_score=80)
    assert issue_detail(m, issue["id"])["verification"]["status"] == "observed_without_score"


def test_with_several_actions_the_baseline_is_before_the_first_and_the_follow_up_after_the_last(sick):
    m, w, tree, issue = sick  # score 30 three hours ago
    act(w, tree["id"], issue_id=issue["id"], performed_at=ago(hours=2))
    observe(w, tree["id"], health_score=55, observed_at=ago(hours=1, minutes=30))  # between the two actions
    act(w, tree["id"], "water", issue_id=issue["id"], performed_at=ago(hours=1))
    v = issue_detail(m, issue["id"])["verification"]
    # neither the baseline (it stays 30) nor a follow-up (none yet): the check between two rounds of work is neither
    assert (v["status"], v["baseline_score"], v["actions"]) == ("awaiting_follow_up", 30, 2)
    observe(w, tree["id"], health_score=60)
    v = issue_detail(m, issue["id"])["verification"]
    assert (v["status"], v["baseline_score"], v["follow_up_score"], v["change"]) == ("improved", 30, 60, 30)


def test_a_closed_issue_keeps_the_verification_it_was_closed_with(sick):
    m, w, tree, issue = sick
    act(w, tree["id"], issue_id=issue["id"])
    assert close(m, issue["id"], follow_up={"health_score": 80}).status_code == 200
    observe(w, tree["id"], health_score=10)  # later events do not rewrite the closing evidence
    v = issue_detail(m, issue["id"])["verification"]
    assert (v["status"], v["follow_up_score"]) == ("improved", 80)


def test_issues_outside_plant_health_are_not_held_to_the_rule(api_for, team):
    m = api_for(team.manager)
    tree = make_asset(m)
    pipe = make_issue(m, tree["id"], title="Drip line broken", category="irrigation_failure")
    for state in ("assigned", "fixed"):
        assert m.post(f"/issues/{pipe['id']}/transitions", {"to_state": state}).status_code == 200
    r = close(m, pipe["id"], state="verified")
    assert r.status_code == 200 and r.json()["verification"]["required_for_success"] is False
    loc = make_location(m)
    zone_issue = make_issue(m, None, location_id=loc["id"])
    v = issue_detail(m, zone_issue["id"])["verification"]
    assert v["status"] == "not_applicable" and v["required_for_success"] is False
    assert close(m, zone_issue["id"]).status_code == 200
    r = close(m, zone_issue["id"], follow_up={"notes": "x"})  # already closed: nothing to move
    assert r.status_code == 409


def test_a_follow_up_needs_an_asset(api_for, team):
    m = api_for(team.manager)
    loc = make_location(m)
    zone_issue = make_issue(m, None, location_id=loc["id"])
    r = close(m, zone_issue["id"], follow_up={"notes": "looked"})
    assert r.status_code == 422 and r.json()["code"] == "issue_has_no_asset"


# ------------------------------------------------------------------ timeline


def test_the_timeline_shows_work_and_corrections(sick):
    m, w, tree, issue = sick
    [a] = act(w, tree["id"], "water", quantity=10, unit="l", note="deep soak").json()["history"]
    correct(m, tree["id"], a["id"], kind="water", quantity=20, unit="l", note="it was two cans, not one")
    items = [e for e in m.get(f"/assets/{tree['id']}/timeline").json() if e["type"] == "action"]
    assert sorted(e["title"] for e in items) == ["Action correction: Watering", "Action: Watering"]
    assert any(e["detail"] == "10 l · deep soak" for e in items)


# ------------------------------------------------------------------ database guarantees (PostgreSQL)


@pg
def test_actions_are_append_only_and_constrained_in_the_database(api_for, team, world):
    m = api_for(team.manager)
    tree = make_asset(m)
    act(m, tree["id"])
    base = (
        "INSERT INTO actions (id, workspace_id, asset_id, kind, quantity, unit, performed_at, note, supersedes_id, "
        "withdrawn, created_at) "
    )
    cases = [
        (
            f"{base}VALUES (gen_random_uuid(), :ws, :a, 'dig', NULL, NULL, now(), NULL, NULL, false, now())",
            "ck_actions_kind",
        ),
        (
            f"{base}VALUES (gen_random_uuid(), :ws, :a, 'water', 2, NULL, now(), NULL, NULL, false, now())",
            "quantity_has_unit",
        ),
        (
            f"{base}VALUES (gen_random_uuid(), :ws, :a, 'water', -1, 'l', now(), NULL, NULL, false, now())",
            "quantity_positive",
        ),
        (
            f"{base}VALUES (gen_random_uuid(), :ws, :a, 'water', NULL, NULL, now(), NULL, NULL, true, now())",
            "withdrawal_is_correction",
        ),
    ]
    with world.db() as db:
        for statement, constraint in cases:
            with pytest.raises(IntegrityError, match=constraint):
                db.execute(text(statement), {"ws": team.ws, "a": tree["id"]})
            db.rollback()
        with pytest.raises(IntegrityError, match="fk_actions_asset"):  # another tenant's workspace id
            db.execute(text(cases[0][0].replace("'dig'", "'water'")), {"ws": team.other_ws, "a": tree["id"]})
        db.rollback()
        for statement in (
            "UPDATE actions SET kind = 'water' WHERE asset_id = :a",
            "DELETE FROM actions WHERE asset_id = :a",
        ):
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(statement), {"a": tree["id"]})
            db.rollback()


@pg
def test_the_database_allows_one_correction_per_action(api_for, team, world):
    m = api_for(team.manager)
    tree = make_asset(m)
    [a] = act(m, tree["id"]).json()["history"]
    correct(m, tree["id"], a["id"])
    sql = (
        "INSERT INTO actions (id, workspace_id, asset_id, kind, performed_at, note, supersedes_id, withdrawn, created_at) "
        "VALUES (gen_random_uuid(), :ws, :a, 'treat', now(), 'a second correction', :s, false, now())"
    )
    with world.db() as db, pytest.raises(IntegrityError, match="uq_actions_supersedes"):
        db.execute(text(sql), {"ws": team.ws, "a": tree["id"], "s": a["id"]})
