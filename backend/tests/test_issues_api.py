"""Botanical Issues as first-class domain objects: workflow, severity, evidence, assignment, resolution, history."""

from __future__ import annotations

import pytest

from tests.helpers import make_asset, make_issue, make_location, make_task, observe, resolve_body


def move(api, issue_id, to_state, **extra):
    return api.post(f"/issues/{issue_id}/transitions", {"to_state": to_state, **extra})


def test_create_an_issue_from_an_observation(api_for, team):
    worker, manager = api_for(team.worker), api_for(team.manager)
    zone = make_location(manager, "Zone 4")
    asset = make_asset(worker, label="Neem #482", location_id=zone["id"])
    obs = observe(worker, asset["id"], health_score=35, symptoms=["leaf_yellowing"])["observation"]

    r = worker.post(
        "/issues",
        {"title": "Neem Tree - Leaf yellowing", "category": "disease", "severity": "high", "observation_id": obs["id"]},
    )
    assert r.status_code == 201, r.text
    issue = r.json()
    assert issue["key"] == "GG-001" and issue["state"] == "open" and issue["is_open"] is True
    assert issue["asset_id"] == asset["id"] and issue["asset_label"] == "Neem #482"  # asset inferred from the evidence
    assert issue["source"] == "observation" and issue["origin_observation_id"] == obs["id"]
    assert issue["reporter_id"] == str(team.worker.id) and issue["severity"] == "high"
    assert [e["id"] for e in issue["evidence"]] == [obs["id"]]
    assert [(h["from_state"], h["to_state"]) for h in issue["history"]] == [(None, "open")]
    assert issue["allowed_transitions"] == ["investigating", "resolved", "closed_wont_fix"]

    st = worker.get(f"/assets/{asset['id']}").json()["state"]
    assert st["open_issue_count"] == 1


def test_issue_keys_are_sequential_per_workspace(api_for, team):
    api = api_for(team.worker)
    a = make_asset(api)
    assert [make_issue(api, a["id"])["key"] for _ in range(3)] == ["GG-001", "GG-002", "GG-003"]
    other = api_for(team.other_owner, team.other_ws)
    assert make_issue(other, make_asset(other)["id"])["key"] == "GG-001"  # separate counter per tenant


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "x"},  # no subject
        {"title": "", "asset_id": "00000000-0000-0000-0000-00000000beef"},
        {"title": "x", "asset_id": "00000000-0000-0000-0000-00000000beef", "severity": "apocalyptic"},
        {"title": "x", "asset_id": "00000000-0000-0000-0000-00000000beef", "category": "witchcraft"},
        {"title": "x", "asset_id": "00000000-0000-0000-0000-00000000beef", "surprise": 1},
    ],
)
def test_issue_validation(api_for, team, payload):
    assert api_for(team.worker).post("/issues", payload).status_code == 422


def test_missing_and_cross_tenant_references_are_404_or_422(api_for, team):
    mine, theirs = api_for(team.worker), api_for(team.other_owner, team.other_ws)
    ghost = "00000000-0000-0000-0000-00000000beef"
    assert mine.post("/issues", {"title": "x", "asset_id": ghost}).json()["code"] == "asset_not_found"
    assert mine.post("/issues", {"title": "x", "observation_id": ghost}).json()["code"] == "observation_not_found"
    foreign_asset = make_asset(theirs)
    foreign_obs = observe(theirs, foreign_asset["id"])["observation"]
    assert mine.post("/issues", {"title": "x", "asset_id": foreign_asset["id"]}).status_code == 404
    assert mine.post("/issues", {"title": "x", "observation_id": foreign_obs["id"]}).status_code == 404
    other_asset = make_asset(mine, label="b")
    own_obs = observe(mine, make_asset(mine, label="a")["id"])["observation"]
    r = mine.post("/issues", {"title": "x", "asset_id": other_asset["id"], "observation_id": own_obs["id"]})
    assert r.status_code == 422 and r.json()["code"] == "observation_asset_mismatch"
    assert theirs.get(f"/issues/{make_issue(mine, other_asset['id'])['id']}").status_code == 404


def test_full_plant_health_lifecycle_with_complete_history(api_for, team):
    worker, manager = api_for(team.worker), api_for(team.manager)
    a = make_asset(worker)
    issue = make_issue(worker, a["id"])
    iid = issue["id"]
    for state in ("investigating", "treatment", "monitoring"):
        r = move(manager, iid, state, note=f"moving to {state}")
        assert r.status_code == 200, r.text
        assert r.json()["state"] == state and r.json()["is_open"] is True
    r = move(manager, iid, "resolved", resolution=resolve_body("fixed", "Fungicide worked; new growth healthy"))
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["state"] == "resolved" and done["is_open"] is False and done["resolved_at"] is not None
    assert done["resolution_outcome"] == "fixed" and done["resolved_by"] == str(team.manager.id)
    assert done["allowed_transitions"] == ["investigating"]  # reopen only
    assert [(h["from_state"], h["to_state"]) for h in done["history"]] == [
        (None, "open"),
        ("open", "investigating"),
        ("investigating", "treatment"),
        ("treatment", "monitoring"),
        ("monitoring", "resolved"),
    ]
    assert done["history"][1]["note"] == "moving to investigating"
    assert done["version"] == 5
    st = worker.get(f"/assets/{a['id']}").json()["state"]
    assert st["open_issue_count"] == 0 and st["last_resolved_at"] is not None  # the asset reflects the resolution


def test_illegal_transitions_are_409_and_list_what_is_allowed(api_for, team):
    manager = api_for(team.manager)
    iid = make_issue(manager, make_asset(manager)["id"])["id"]
    r = move(manager, iid, "monitoring")  # open -> monitoring is not in the plant_health workflow
    assert r.status_code == 409 and r.json()["code"] == "invalid_transition"
    assert r.json()["allowed"] == ["investigating", "resolved", "closed_wont_fix"]
    assert move(manager, iid, "teleported").json()["code"] == "unknown_state"
    assert manager.get(f"/issues/{iid}").json()["state"] == "open"  # nothing changed


def test_closing_requires_a_consistent_resolution(api_for, team):
    manager = api_for(team.manager)
    iid = make_issue(manager, make_asset(manager)["id"])["id"]
    assert move(manager, iid, "resolved").json()["code"] == "resolution_required"
    r = move(manager, iid, "resolved", resolution=resolve_body("wont_fix"))
    assert r.status_code == 422 and r.json()["code"] == "outcome_mismatch"
    r = move(manager, iid, "closed_wont_fix", resolution=resolve_body("fixed"))
    assert r.json()["code"] == "outcome_mismatch"
    r = move(manager, iid, "closed_wont_fix", resolution={"outcome": "wont_fix"})
    assert r.json()["code"] == "notes_required"
    ok = move(manager, iid, "closed_wont_fix", resolution=resolve_body("wont_fix", "Tree is scheduled for removal"))
    assert ok.status_code == 200 and ok.json()["resolution_outcome"] == "wont_fix" and ok.json()["is_open"] is False


def test_open_tasks_block_resolution_unless_explicitly_cancelled(api_for, team):
    manager = api_for(team.manager)
    a = make_asset(manager)
    iid = make_issue(manager, a["id"])["id"]
    t1 = make_task(manager, issue_id=iid, title="Spray")
    t2 = make_task(manager, issue_id=iid, title="Recheck")
    r = move(manager, iid, "resolved", resolution=resolve_body())
    assert r.status_code == 409 and r.json()["code"] == "open_tasks" and sorted(r.json()["tasks"]) == ["T-001", "T-002"]

    r = move(manager, iid, "resolved", resolution=resolve_body(cancel_open_tasks=True))
    assert r.status_code == 200
    for t in (t1, t2):
        task = manager.get(f"/tasks/{t['id']}").json()
        assert task["status"] == "cancelled"
        assert task["history"][-1]["note"] == "Cancelled when GG-001 was closed"  # auditable
    st = manager.get(f"/assets/{a['id']}").json()["state"]
    assert st["open_task_count"] == 0 and st["open_issue_count"] == 0


def test_reopening_clears_the_resolution_but_history_remembers(api_for, team):
    manager = api_for(team.manager)
    iid = make_issue(manager, make_asset(manager)["id"])["id"]
    move(manager, iid, "resolved", resolution=resolve_body("mitigated", "looked fine"))
    r = move(manager, iid, "investigating")
    body = r.json()
    assert r.status_code == 200 and body["is_open"] is True and body["resolution_outcome"] is None
    assert body["resolved_at"] is None and body["resolved_by"] is None
    assert [h["to_state"] for h in body["history"]] == ["open", "resolved", "investigating"]
    assert body["history"][-1]["note"] == "Reopened"


def test_workflow_depends_on_category_and_workspace_mode(api_for, team):
    green, agri = api_for(team.owner), api_for(team.owner, team.agri_ws)
    cases = [
        (green, "disease", "plant_health", "open"),
        (agri, "disease", "field_disease", "open"),
        (agri, "pest", "field_disease", "open"),
        (agri, "nutrient", "plant_health", "open"),
        (green, "irrigation_failure", "infrastructure", "open"),
        (agri, "harvest_readiness", "harvest_readiness", "pending"),
    ]
    for api, category, workflow, initial in cases:
        a = make_asset(api, label=f"{category}-asset")
        issue = make_issue(api, a["id"], category=category)
        assert (issue["workflow_key"], issue["state"]) == (workflow, initial), category
    # field disease uses the agricultural vocabulary: field_inspection instead of investigating
    a = make_asset(agri, label="tomatoes")
    iid = make_issue(agri, a["id"], title="Possible fungal infection", category="disease")["id"]
    assert move(agri, iid, "investigating").status_code == 409
    assert move(agri, iid, "field_inspection").status_code == 200


def test_infrastructure_workflow_ends_in_verified(api_for, team):
    api = api_for(team.owner)
    iid = make_issue(api, make_asset(api)["id"], title="Drip line broken", category="irrigation_failure")["id"]
    assert move(api, iid, "assigned").status_code == 200
    assert move(api, iid, "fixed").status_code == 200
    r = move(api, iid, "verified", resolution=resolve_body("fixed", "Pressure normal"))
    assert r.status_code == 200 and r.json()["is_open"] is False


def test_workflows_endpoint_exposes_states_so_clients_do_not_hard_code_them(api_for, team):
    flows = {w["key"]: w for w in api_for(team.viewer).get("/issues/workflows").json()}
    assert {"plant_health", "field_disease", "infrastructure", "harvest_readiness"} <= set(flows)
    assert flows["plant_health"]["states"][:5] == ["open", "investigating", "treatment", "monitoring", "resolved"]
    assert "closed_wont_fix" in flows["plant_health"]["terminal"]


def test_updates_are_audited_and_assignee_must_be_a_member(api_for, team):
    manager, worker = api_for(team.manager), api_for(team.worker)
    iid = make_issue(manager, make_asset(manager)["id"], severity="low")["id"]
    r = manager.patch(f"/issues/{iid}", {"severity": "critical", "assignee_id": str(team.worker.id)})
    assert r.status_code == 200
    body = r.json()
    assert body["severity"] == "critical" and body["assignee_id"] == str(team.worker.id) and body["version"] == 2
    audit = body["history"][-1]
    assert audit["from_state"] == audit["to_state"] == "open"
    assert "severity low → critical" in audit["note"] and "reassigned" in audit["note"]
    bad = manager.patch(f"/issues/{iid}", {"assignee_id": str(team.outsider.id)})
    assert bad.status_code == 422 and bad.json()["code"] == "assignee_not_member"
    assert worker.patch(f"/issues/{iid}", {"severity": "low"}).status_code == 403
    assert manager.patch(f"/issues/{iid}", {"severity": "critical"}).json()["version"] == 2  # no-op: no new version


def test_extra_evidence_can_be_attached(api_for, team):
    worker = api_for(team.worker)
    a, b = make_asset(worker, label="a"), make_asset(worker, label="b")
    first = observe(worker, a["id"], health_score=40)["observation"]
    later = observe(worker, a["id"], health_score=35)["observation"]
    foreign = observe(worker, b["id"])["observation"]
    iid = make_issue(worker, a["id"], observation_id=first["id"])["id"]
    r = worker.post(f"/issues/{iid}/evidence", {"observation_id": later["id"]})
    assert r.status_code == 200 and [e["id"] for e in r.json()["evidence"]] == [first["id"], later["id"]]
    assert (
        len(worker.post(f"/issues/{iid}/evidence", {"observation_id": later["id"]}).json()["evidence"]) == 2
    )  # idempotent
    assert (
        worker.post(f"/issues/{iid}/evidence", {"observation_id": foreign["id"]}).json()["code"]
        == "observation_asset_mismatch"
    )


def test_listing_filters_and_roles(api_for, team):
    worker, manager, viewer = api_for(team.worker), api_for(team.manager), api_for(team.viewer)
    a = make_asset(worker)
    i1 = make_issue(worker, a["id"], title="Aphids", category="pest", severity="high")
    i2 = make_issue(worker, a["id"], title="Dry soil", category="water_stress", severity="low")
    move(manager, i2["id"], "resolved", resolution=resolve_body())
    assert viewer.get("/issues").json()["total"] == 2
    assert [i["key"] for i in viewer.get("/issues", params={"is_open": True}).json()["items"]] == [i1["key"]]
    assert [i["key"] for i in viewer.get("/issues", params={"severity": "low"}).json()["items"]] == [i2["key"]]
    assert viewer.get("/issues", params={"q": "aphid"}).json()["total"] == 1
    assert viewer.get("/issues", params={"asset_id": a["id"], "category": "pest"}).json()["total"] == 1
    assert viewer.get("/issues", params={"assignee": "not-a-uuid"}).status_code == 422
    assert viewer.post("/issues", {"title": "x", "asset_id": a["id"]}).status_code == 403
    assert worker.post(f"/issues/{i1['id']}/transitions", {"to_state": "investigating"}).status_code == 403
