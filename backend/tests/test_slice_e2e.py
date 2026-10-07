"""The first vertical slice, end to end, through the public API only:

REGISTER -> MONITOR -> OBSERVE -> DETECT -> CREATE ISSUE -> CREATE TASK -> TAKE ACTION -> RESOLVE -> UPDATE ASSET
"""

from __future__ import annotations

from tests.helpers import ago, make_location, species_id


def test_the_operational_loop_from_registration_to_updated_state(api_for, team):
    manager, worker = api_for(team.manager), api_for(team.worker)

    # REGISTER: a Neem tree in Ward 42 / Zone 4
    zone = make_location(manager, "Ward 42 Zone 4", "zone")
    tree = worker.post(
        "/assets",
        {
            "label": "Neem Tree #482",
            "kind": "tree",
            "species_id": species_id(worker, "Neem"),
            "location_id": zone["id"],
            "tag_code": "W42-482",
            "latitude": 19.2012,
            "longitude": 72.9701,
            "planted_at": "2024-07-15",
        },
    ).json()
    aid = tree["id"]
    assert tree["state"]["health_band"] is None  # nothing is known yet, and the system says so

    # MONITOR / OBSERVE: a healthy baseline, then a worrying inspection a week later
    baseline = worker.post("/observations", {"asset_id": aid, "health_score": 86, "observed_at": ago(days=8)}).json()
    assert baseline["recommendations"] == []
    worry = worker.post(
        "/observations",
        {
            "asset_id": aid,
            "health_score": 31,
            "symptoms": ["leaf_yellowing", "leaf_drop"],
            "notes": "canopy thinning",
            "attachments": [{"name": "canopy.jpg", "content_type": "image/jpeg", "url": "https://example.com/c.jpg"}],
        },
    ).json()
    state = worker.get(f"/assets/{aid}").json()["state"]
    assert state["health_score"] == 31 and state["health_band"] == "critical"  # CURRENT STATE

    # DETECT: the rule-based agent flagged it, with the reason, right after the observation
    [rec] = worry["recommendations"]
    assert rec["rule_key"] == "critical_health" and rec["method"] == "rule"
    assert "below the critical threshold" in rec["explanation"]
    assert manager.get("/recommendations").json()["total"] == 1

    # CREATE ISSUE: a manager accepts the recommendation, which opens a Botanical Issue with the evidence attached
    accepted = manager.post(
        f"/recommendations/{rec['id']}/accept", {"assignee_id": str(team.worker.id), "severity": "high"}
    ).json()
    issue_id = accepted["accepted_entity_id"]
    issue = manager.get(f"/issues/{issue_id}").json()
    assert (issue["key"], issue["state"], issue["source"]) == ("GG-001", "open", "agent")
    assert issue["evidence"][0]["id"] == worry["observation"]["id"]
    assert manager.get(f"/assets/{aid}").json()["state"]["open_issue_count"] == 1

    # the issue moves through its workflow
    for state in ("investigating", "treatment"):
        assert manager.post(f"/issues/{issue_id}/transitions", {"to_state": state}).status_code == 200

    # CREATE TASK: assign the treatment, with a due date
    task = manager.post(
        "/tasks",
        {
            "title": "Apply neem-oil spray and mulch",
            "type": "treat",
            "issue_id": issue_id,
            "assignee_id": str(team.worker.id),
            "priority": "p1",
            "due_at": ago(days=-2),
        },
    ).json()
    assert task["key"] == "T-001" and task["asset_id"] == aid and task["status"] == "todo"
    assert manager.get(f"/assets/{aid}").json()["state"]["open_task_count"] == 1

    # the issue cannot be closed while the work is still open
    blocked = manager.post(
        f"/issues/{issue_id}/transitions",
        {"to_state": "resolved", "resolution": {"outcome": "fixed", "notes": "too early"}},
    )
    assert blocked.status_code == 409 and blocked.json()["code"] == "open_tasks"

    # TAKE ACTION: the assigned worker does the work and records what they found
    assert worker.post(f"/tasks/{task['id']}/transitions", {"to_status": "in_progress"}).status_code == 200
    done = worker.post(
        f"/tasks/{task['id']}/transitions",
        {
            "to_status": "done",
            "note": "sprayed, mulched, staked",
            "observation": {"health_score": 68, "symptoms": [], "notes": "new leaf flush visible"},
        },
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "done"

    # UPDATE ASSET: its state already reflects the follow-up (health recovered, work no longer open)
    state = worker.get(f"/assets/{aid}").json()["state"]
    assert state["health_score"] == 68 and state["health_band"] == "at_risk"
    assert state["open_task_count"] == 0 and state["open_issue_count"] == 1

    # MONITOR the result, then RESOLVE with an outcome
    assert manager.post(f"/issues/{issue_id}/transitions", {"to_state": "monitoring"}).status_code == 200
    resolved = manager.post(
        f"/issues/{issue_id}/transitions",
        {"to_state": "resolved", "resolution": {"outcome": "fixed", "notes": "Recovered after treatment"}},
    ).json()
    assert resolved["is_open"] is False and resolved["resolution_outcome"] == "fixed"

    # final asset state
    final = manager.get(f"/assets/{aid}").json()
    assert final["state"]["open_issue_count"] == 0 and final["state"]["open_task_count"] == 0
    assert final["state"]["last_resolved_at"] is not None and final["state"]["health_score"] == 68

    # the agent stays quiet: the score is above the critical threshold and nothing is overdue
    assert manager.post("/agent/run").json()["created"] == []

    # HISTORY: everything that happened is preserved, newest first
    timeline = manager.get(f"/assets/{aid}/timeline").json()
    kinds = [e["type"] for e in timeline]
    assert kinds.count("observation") == 3  # baseline, worry, follow-up
    issue_events = [e["detail"] for e in timeline if e["type"] == "issue"]
    assert any("opened as open" in d for d in issue_events) and any("monitoring → resolved" in d for d in issue_events)
    task_events = [e["detail"] for e in timeline if e["type"] == "task"]
    assert any("in_progress → done" in d for d in task_events)
    assert [e["at"] for e in timeline] == sorted((e["at"] for e in timeline), reverse=True)

    final_issue = manager.get(f"/issues/{issue_id}").json()
    assert [h["to_state"] for h in final_issue["history"]] == [
        "open",
        "investigating",
        "treatment",
        "monitoring",
        "resolved",
    ]
    assert final_issue["tasks"][0]["status"] == "done"
    assert len(final_issue["evidence"]) == 1


def test_the_same_loop_works_for_an_agricultural_crop_batch(api_for, team):
    """No separate 'tree system': a crop batch in a field walks the same model with the agricultural workflow."""
    api = api_for(team.owner, team.agri_ws)
    field = make_location(api, "Field 3", "field")
    batch = api.post(
        "/assets",
        {
            "label": "Tomato Batch #17",
            "kind": "crop_batch",
            "tracking_mode": "population",
            "estimated_count": 84200,
            "species_id": species_id(api, "Tomato"),
            "location_id": field["id"],
        },
    ).json()
    obs = api.post("/observations", {"asset_id": batch["id"], "health_score": 33, "symptoms": ["leaf_spot"]}).json()
    rec = obs["recommendations"][0]
    issue_id = api.post(f"/recommendations/{rec['id']}/accept", {"severity": "high"}).json()["accepted_entity_id"]
    issue = api.get(f"/issues/{issue_id}").json()
    assert issue["workflow_key"] == "plant_health" and issue["category"] == "growth_anomaly"
    # a manual disease issue in an agricultural workspace uses the field-disease workflow
    manual = api.post(
        "/issues", {"title": "Possible fungal infection", "asset_id": batch["id"], "category": "disease"}
    ).json()
    assert manual["workflow_key"] == "field_disease"
    assert api.post(f"/issues/{manual['id']}/transitions", {"to_state": "field_inspection"}).status_code == 200
