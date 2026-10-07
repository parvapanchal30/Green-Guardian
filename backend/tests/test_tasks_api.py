"""Tasks: assigned work with owners, due dates and a status history; completing work updates the asset."""

from __future__ import annotations

import pytest

from tests.helpers import ago, ahead, make_asset, make_issue, make_task, observe, resolve_body


def go(api, task_id, to_status, **extra):
    return api.post(f"/tasks/{task_id}/transitions", {"to_status": to_status, **extra})


def test_create_a_task_for_an_issue_assign_it_and_set_a_due_date(api_for, team):
    manager = api_for(team.manager)
    asset = make_asset(manager, label="Neem #482")
    issue = make_issue(manager, asset["id"])
    due = ahead(days=2)
    r = manager.post(
        "/tasks",
        {
            "title": "Apply neem-oil spray",
            "type": "treat",
            "issue_id": issue["id"],
            "assignee_id": str(team.worker.id),
            "priority": "p1",
            "due_at": due,
        },
    )
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["key"] == "T-001" and t["status"] == "todo" and t["source"] == "issue"
    assert t["issue_id"] == issue["id"] and t["issue_key"] == "GG-001"
    assert t["asset_id"] == asset["id"] and t["asset_label"] == "Neem #482"  # inherited from the issue
    assert t["assignee_id"] == str(team.worker.id) and t["priority"] == "p1" and t["overdue"] is False
    assert [(h["from_status"], h["to_status"]) for h in t["history"]] == [(None, "todo")]
    assert t["allowed_transitions"] == ["in_progress", "blocked", "done", "cancelled"]
    assert manager.get(f"/assets/{asset['id']}").json()["state"]["open_task_count"] == 1
    assert [x["id"] for x in manager.get(f"/issues/{issue['id']}").json()["tasks"]] == [t["id"]]


def test_task_status_changes_as_work_progresses_with_full_history(api_for, team):
    manager, worker = api_for(team.manager), api_for(team.worker)
    asset = make_asset(manager)
    t = make_task(manager, asset_id=asset["id"], assignee_id=str(team.worker.id))
    assert go(worker, t["id"], "in_progress", note="on my way").json()["started_at"] is not None
    assert go(worker, t["id"], "blocked", note="locked gate").json()["status"] == "blocked"
    assert go(worker, t["id"], "in_progress").status_code == 200
    done = go(worker, t["id"], "done", note="sprayed both sides").json()
    assert (
        done["status"] == "done"
        and done["completed_at"] is not None
        and done["completion_notes"] == "sprayed both sides"
    )
    assert [(h["from_status"], h["to_status"]) for h in done["history"]] == [
        (None, "todo"),
        ("todo", "in_progress"),
        ("in_progress", "blocked"),
        ("blocked", "in_progress"),
        ("in_progress", "done"),
    ]
    assert all(h["actor_id"] for h in done["history"][1:])
    assert manager.get(f"/assets/{asset['id']}").json()["state"]["open_task_count"] == 0


def test_invalid_task_transitions_are_409_with_the_allowed_set(api_for, team):
    manager = api_for(team.manager)
    t = make_task(manager)
    r = go(manager, t["id"], "todo")  # todo -> todo
    assert r.status_code == 409 and r.json()["code"] == "invalid_transition"
    go(manager, t["id"], "cancelled")
    r = go(manager, t["id"], "done")
    assert r.status_code == 409 and r.json()["allowed"] == ["todo"]


def test_only_the_assignee_or_a_manager_may_change_status(api_for, team):
    manager, worker, viewer = api_for(team.manager), api_for(team.worker), api_for(team.viewer)
    mine = make_task(manager, title="mine", assignee_id=str(team.worker.id))
    not_mine = make_task(manager, title="someone else's")
    unassigned_move = go(worker, not_mine["id"], "in_progress")
    assert unassigned_move.status_code == 403 and unassigned_move.json()["code"] == "not_assignee"
    assert go(viewer, mine["id"], "in_progress").status_code == 403
    assert go(worker, mine["id"], "in_progress").status_code == 200
    assert go(manager, not_mine["id"], "in_progress").status_code == 200  # managers can move any task


def test_only_a_manager_can_reopen(api_for, team):
    manager, worker = api_for(team.manager), api_for(team.worker)
    t = make_task(manager, assignee_id=str(team.worker.id))
    go(worker, t["id"], "done")
    r = go(worker, t["id"], "in_progress")
    assert r.status_code == 403 and r.json()["code"] == "insufficient_role"
    reopened = go(manager, t["id"], "in_progress").json()
    assert reopened["status"] == "in_progress" and reopened["completed_at"] is None


def test_completing_a_task_with_a_follow_up_observation_updates_the_asset(api_for, team):
    """ACT -> UPDATE ASSET: the work records what was found, and the asset's state follows."""
    manager, worker = api_for(team.manager), api_for(team.worker)
    asset = make_asset(manager)
    observe(manager, asset["id"], health_score=30, observed_at=ago(days=1))
    t = make_task(manager, asset_id=asset["id"], type="treat", assignee_id=str(team.worker.id))
    assert manager.get(f"/assets/{asset['id']}").json()["state"]["health_band"] == "critical"
    go(worker, t["id"], "in_progress")
    r = go(
        worker, t["id"], "done", note="treated", observation={"health_score": 72, "notes": "new growth after spraying"}
    )
    assert r.status_code == 200, r.text
    st = manager.get(f"/assets/{asset['id']}").json()["state"]
    assert st["health_score"] == 72 and st["health_band"] == "healthy" and st["open_task_count"] == 0
    obs = manager.get("/observations", params={"asset_id": asset["id"]}).json()["items"]
    assert (
        len(obs) == 2
        and obs[0]["notes"] == "new growth after spraying"
        and obs[0]["observer_id"] == str(team.worker.id)
    )


@pytest.mark.parametrize(
    "to_status,body,code",
    [
        ("in_progress", {"observation": {"health_score": 50}}, "observation_needs_done"),
        ("done", {"observation": {"health_score": 500}}, None),
    ],
)
def test_follow_up_observation_rules(api_for, team, to_status, body, code):
    manager = api_for(team.manager)
    asset = make_asset(manager)
    t = make_task(manager, asset_id=asset["id"])
    r = go(manager, t["id"], to_status, **body)
    assert r.status_code == 422
    if code:
        assert r.json()["code"] == code
    assert manager.get(f"/tasks/{t['id']}").json()["status"] == "todo"  # nothing was half-applied


def test_a_task_without_an_asset_cannot_carry_an_observation(api_for, team):
    manager = api_for(team.manager)
    t = make_task(manager)
    r = go(manager, t["id"], "done", observation={"health_score": 50})
    assert r.status_code == 422 and r.json()["code"] == "task_has_no_asset"


def test_task_validation_and_references(api_for, team):
    manager, other = api_for(team.manager), api_for(team.other_owner, team.other_ws)
    a = make_asset(manager)
    ghost = "00000000-0000-0000-0000-00000000beef"
    assert manager.post("/tasks", {"title": ""}).status_code == 422
    assert manager.post("/tasks", {"title": "x", "priority": "p9"}).status_code == 422
    assert manager.post("/tasks", {"title": "x", "type": "teleport"}).status_code == 422
    assert manager.post("/tasks", {"title": "x", "issue_id": ghost}).json()["code"] == "issue_not_found"
    assert manager.post("/tasks", {"title": "x", "asset_id": ghost}).json()["code"] == "asset_not_found"
    bad = manager.post("/tasks", {"title": "x", "assignee_id": str(team.outsider.id)})
    assert bad.status_code == 422 and bad.json()["code"] == "assignee_not_member"
    assert other.post("/tasks", {"title": "x", "asset_id": a["id"]}).status_code == 404  # another tenant's asset
    foreign_task = make_task(other)
    assert manager.get(f"/tasks/{foreign_task['id']}").status_code == 404
    assert go(manager, foreign_task["id"], "done").status_code == 404


def test_a_closed_issue_does_not_accept_new_tasks_until_reopened(api_for, team):
    manager = api_for(team.manager)
    iid = make_issue(manager, make_asset(manager)["id"])["id"]
    manager.post(f"/issues/{iid}/transitions", {"to_state": "resolved", "resolution": resolve_body()})
    r = manager.post("/tasks", {"title": "late work", "issue_id": iid})
    assert r.status_code == 422 and r.json()["code"] == "issue_closed"
    manager.post(f"/issues/{iid}/transitions", {"to_state": "investigating"})
    assert manager.post("/tasks", {"title": "late work", "issue_id": iid}).status_code == 201


def test_updates_are_audited_and_role_gated(api_for, team):
    manager, worker = api_for(team.manager), api_for(team.worker)
    t = make_task(manager)
    r = manager.patch(
        f"/tasks/{t['id']}", {"priority": "p1", "due_at": ahead(days=1), "assignee_id": str(team.worker.id)}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["priority"] == "p1" and body["assignee_id"] == str(team.worker.id) and body["version"] == 2
    note = body["history"][-1]["note"]
    assert "priority p3 → p1" in note and "due date changed" in note and "reassigned" in note
    assert worker.patch(f"/tasks/{t['id']}", {"priority": "p4"}).status_code == 403
    cleared = manager.patch(f"/tasks/{t['id']}", {"due_at": None}).json()
    assert cleared["due_at"] is None


def test_listing_my_tasks_overdue_and_ordering(api_for, team):
    manager, worker = api_for(team.manager), api_for(team.worker)
    late = make_task(manager, title="late", assignee_id=str(team.worker.id), due_at=ago(days=1))
    soon = make_task(manager, title="soon", assignee_id=str(team.worker.id), due_at=ahead(days=1))
    make_task(manager, title="nobody", due_at=ahead(days=5))
    make_task(manager, title="no date", assignee_id=str(team.worker.id))
    done = make_task(manager, title="done one", assignee_id=str(team.worker.id))
    go(manager, done["id"], "done")

    mine = worker.get("/tasks", params={"assignee": "me", "is_open": True}).json()
    assert [t["title"] for t in mine["items"]] == ["late", "soon", "no date"]  # nearest due first, undated last
    assert mine["items"][0]["overdue"] is True and mine["items"][1]["overdue"] is False
    assert [t["id"] for t in worker.get("/tasks", params={"overdue": True}).json()["items"]] == [late["id"]]
    assert worker.get("/tasks", params={"assignee": "unassigned"}).json()["total"] == 1
    assert worker.get("/tasks", params={"status": "done"}).json()["total"] == 1
    assert worker.get("/tasks", params={"q": "soon"}).json()["items"][0]["id"] == soon["id"]
    assert worker.get("/tasks", params={"assignee": "nonsense"}).status_code == 422
    assert api_for(team.viewer).get("/tasks").json()["total"] == 5
    assert api_for(team.viewer).post("/tasks", {"title": "x"}).status_code == 403
    assert worker.post("/tasks", {"title": "x"}).status_code == 403  # planning work is a manager's job
