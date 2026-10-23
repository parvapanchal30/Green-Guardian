"""A compact run of the whole operational loop on real PostgreSQL, using as few requests as possible.

The complete API suite runs on PostgreSQL in CI (local container). Against a distant hosted database (~130 ms per
round trip) the full suite is impractical, so this smoke test is what proves the loop on that kind of database:

    REGISTER -> OBSERVE -> DETECT -> ISSUE -> TASK -> ACT (+follow-up) -> RESOLVE -> UPDATED STATE + HISTORY
"""

from __future__ import annotations

from tests.conftest import requires_pg_mode

pg = requires_pg_mode


@pg
def test_the_operational_loop_on_postgresql(api_for, team):
    manager, worker = api_for(team.manager), api_for(team.worker)

    tree = worker.post("/assets", {"label": "Neem #1", "kind": "tree", "latitude": 19.2, "longitude": 72.97}).json()
    aid = tree["id"]
    worry = worker.post("/observations", {"asset_id": aid, "health_score": 25, "symptoms": ["leaf_drop"]}).json()
    [rec] = worry["recommendations"]
    assert rec["rule_key"] == "critical_health" and rec["method"] == "rule"

    issue_id = manager.post(f"/recommendations/{rec['id']}/accept", {"assignee_id": str(team.worker.id)}).json()[
        "accepted_entity_id"
    ]
    task = manager.post(
        "/tasks", {"title": "Treat", "type": "treat", "issue_id": issue_id, "assignee_id": str(team.worker.id)}
    ).json()
    done = worker.post(
        f"/tasks/{task['id']}/transitions",
        {"to_status": "done", "note": "treated", "observation": {"health_score": 78, "notes": "recovering"}},
    )
    assert done.status_code == 200, done.text

    resolved = manager.post(
        f"/issues/{issue_id}/transitions",
        {"to_state": "resolved", "resolution": {"outcome": "fixed", "notes": "recovered"}},
    ).json()
    assert resolved["is_open"] is False and [h["to_state"] for h in resolved["history"]] == ["open", "resolved"]

    state = manager.get(f"/assets/{aid}").json()["state"]
    assert state["health_score"] == 78 and state["health_band"] == "healthy"
    assert state["open_issue_count"] == 0 and state["open_task_count"] == 0 and state["last_resolved_at"] is not None

    timeline = manager.get(f"/assets/{aid}/timeline").json()
    # registration records the starting stage, so the lifecycle has its own entry
    assert {e["type"] for e in timeline} == {"lifecycle", "observation", "issue", "task"}
    assert sum(e["type"] == "observation" for e in timeline) == 2
