"""Recommendation lifecycle: traceability from advice to action to outcome, and expiry of advice that no longer applies."""

from __future__ import annotations

from tests.helpers import make_asset, observe, resolve_body
from tests.test_agent_api import age_asset


def one(api, rule_key, status="open"):
    items = [
        r for r in api.get("/recommendations", params={"status": status}).json()["items"] if r["rule_key"] == rule_key
    ]
    assert len(items) == 1, items
    return items[0]


def stale_asset(api, world, label="Neglected tree"):
    a = make_asset(api, label=label)
    age_asset(world, a["id"], 40)
    return a


def test_inspection_advice_leads_to_a_task_and_its_completion_is_recorded(api_for, team, world):
    manager = api_for(team.manager)
    a = stale_asset(manager, world)
    run = manager.post("/agent/run").json()
    rec = one(manager, "inspection_gap")
    assert rec["asset_id"] == a["id"] and rec["agent_run_id"] == run["run"]["id"] and rec["rule_version"] == 2
    ev = rec["evidence"]
    assert ev["rule"] == {"key": "inspection_gap", "version": 2} and ev["evaluated_at"] and ev["inputs"]

    accepted = manager.post(f"/recommendations/{rec['id']}/accept", {}).json()
    task = manager.get(f"/tasks/{accepted['accepted_entity_id']}").json()
    assert task["source"] == "agent" and task["recommendation_id"] == rec["id"] and accepted["outcome"] is None

    manager.post(f"/tasks/{task['id']}/transitions", {"to_status": "in_progress"})
    assert manager.get("/recommendations", params={"status": "accepted"}).json()["items"][0]["outcome"] is None
    manager.post(f"/tasks/{task['id']}/transitions", {"to_status": "done"})
    done = one(manager, "inspection_gap", "accepted")
    assert done["outcome"] == "task_completed" and done["outcome_at"] and task["key"] in (done["outcome_detail"] or "")


def test_a_cancelled_task_is_recorded_as_such(api_for, team, world):
    manager = api_for(team.manager)
    stale_asset(manager, world)
    manager.post("/agent/run")
    rec = one(manager, "inspection_gap")
    task_id = manager.post(f"/recommendations/{rec['id']}/accept", {}).json()["accepted_entity_id"]
    manager.post(f"/tasks/{task_id}/transitions", {"to_status": "cancelled"})
    assert one(manager, "inspection_gap", "accepted")["outcome"] == "task_cancelled"


def test_issue_advice_records_resolution_and_the_first_outcome_wins(api_for, team):
    manager = api_for(team.manager)
    a = make_asset(manager, label="Sick tree")
    observe(manager, a["id"], health_score=20)
    rec = one(manager, "critical_health")
    issue_id = manager.post(f"/recommendations/{rec['id']}/accept", {}).json()["accepted_entity_id"]
    r = manager.post(f"/issues/{issue_id}/transitions", {"to_state": "resolved", "resolution": resolve_body()})
    assert r.status_code == 200, r.text
    got = one(manager, "critical_health", "accepted")
    assert got["outcome"] == "issue_resolved" and got["outcome_at"]
    first_at = got["outcome_at"]
    # reopening and resolving again does not rewrite what was recorded first
    manager.post(f"/issues/{issue_id}/transitions", {"to_state": "investigating"})
    manager.post(f"/issues/{issue_id}/transitions", {"to_state": "resolved", "resolution": resolve_body("mitigated")})
    again = one(manager, "critical_health", "accepted")
    assert again["outcome"] == "issue_resolved" and again["outcome_at"] == first_at


def test_an_issue_closed_without_fixing_is_recorded_as_closed(api_for, team):
    manager = api_for(team.manager)
    a = make_asset(manager, label="Condemned tree")
    observe(manager, a["id"], health_score=18)
    rec = one(manager, "critical_health")
    issue_id = manager.post(f"/recommendations/{rec['id']}/accept", {}).json()["accepted_entity_id"]
    manager.post(
        f"/issues/{issue_id}/transitions",
        {"to_state": "closed_wont_fix", "resolution": resolve_body("wont_fix", "Scheduled for removal")},
    )
    assert one(manager, "critical_health", "accepted")["outcome"] == "issue_closed"


def test_work_that_did_not_come_from_advice_records_no_outcome_and_does_not_fail(api_for, team):
    manager = api_for(team.manager)
    a = make_asset(manager)
    from tests.helpers import make_issue

    issue = make_issue(manager, a["id"])
    r = manager.post(f"/issues/{issue['id']}/transitions", {"to_state": "resolved", "resolution": resolve_body()})
    assert r.status_code == 200 and manager.get("/recommendations", params={"status": "accepted"}).json()["items"] == []


def test_advice_expires_when_its_premise_no_longer_holds(api_for, team, world):
    manager = api_for(team.manager)
    a = stale_asset(manager, world)
    manager.post("/agent/run")
    rec = one(manager, "inspection_gap")
    observe(manager, a["id"], health_score=85)  # someone looked at the tree: the inline evaluation on save expires it
    assert manager.get("/recommendations").json()["items"] == []
    assert manager.post("/agent/run").json()["expired"] == 0  # nothing left to expire; no duplicate bookkeeping
    expired = one(manager, "inspection_gap", "expired")
    assert expired["id"] == rec["id"] and expired["agent_run_id"] == rec["agent_run_id"]  # kept, not deleted
    assert expired["evidence"]["expired"]["reason"] and expired["evidence"]["inputs"]  # why, and what it once saw
    assert manager.post(f"/recommendations/{rec['id']}/accept", {}).status_code == 409  # cannot act on expired advice


def test_a_completed_inspection_counts_as_attention_and_silences_the_gap_rule(api_for, team, world):
    manager = api_for(team.manager)
    a = stale_asset(manager, world)
    manager.post("/agent/run")
    rec = one(manager, "inspection_gap")
    task_id = manager.post(f"/recommendations/{rec['id']}/accept", {}).json()["accepted_entity_id"]
    manager.post(f"/tasks/{task_id}/transitions", {"to_status": "in_progress"})
    manager.post(f"/tasks/{task_id}/transitions", {"to_status": "done"})
    out = manager.post("/agent/run").json()
    assert [r for r in out["created"] if r["rule_key"] == "inspection_gap" and r["asset_id"] == a["id"]] == []


def test_an_open_inspection_task_prevents_a_duplicate_operational_action(api_for, team, world):
    manager = api_for(team.manager)
    stale_asset(manager, world)
    manager.post("/agent/run")
    rec = one(manager, "inspection_gap")
    manager.post(f"/recommendations/{rec['id']}/accept", {})
    again = manager.post("/agent/run").json()
    assert [r for r in again["created"] if r["rule_key"] == "inspection_gap"] == []
    tasks = [t for t in manager.get("/tasks").json()["items"] if t["type"] == "inspect"]
    assert len(tasks) == 1
