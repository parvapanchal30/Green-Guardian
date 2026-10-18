"""Tenant isolation and RBAC. Every workspace-scoped endpoint must appear in ENDPOINTS so a new route
cannot ship without an isolation check (CLAUDE.md non-negotiable)."""

from __future__ import annotations

import pytest

# (method, path template, json body) — {ws} and {user_id} are filled in per test.
ENDPOINTS = [
    ("GET", "/api/v1/workspaces/{ws}", None),
    ("PATCH", "/api/v1/workspaces/{ws}", {"name": "hijack"}),
    ("GET", "/api/v1/workspaces/{ws}/capabilities", None),
    ("GET", "/api/v1/workspaces/{ws}/members", None),
    ("POST", "/api/v1/workspaces/{ws}/members", {"email": "x@example.com", "role": "worker"}),
    ("PATCH", "/api/v1/workspaces/{ws}/members/{user_id}", {"role": "viewer"}),
    ("DELETE", "/api/v1/workspaces/{ws}/members/{user_id}", None),
    ("GET", "/api/v1/workspaces/{ws}/weather?lat=19.2&lon=72.9", None),
    # locations / catalog
    ("GET", "/api/v1/workspaces/{ws}/locations", None),
    ("POST", "/api/v1/workspaces/{ws}/locations", {"name": "x", "kind": "zone"}),
    ("GET", "/api/v1/workspaces/{ws}/locations/{location_id}", None),
    ("GET", "/api/v1/workspaces/{ws}/species", None),
    ("POST", "/api/v1/workspaces/{ws}/species", {"category": "tree", "common_name": "x"}),
    # assets
    ("GET", "/api/v1/workspaces/{ws}/assets", None),
    ("POST", "/api/v1/workspaces/{ws}/assets", {"label": "x", "kind": "tree"}),
    ("GET", "/api/v1/workspaces/{ws}/assets/{asset_id}", None),
    ("PATCH", "/api/v1/workspaces/{ws}/assets/{asset_id}", {"label": "x"}),
    ("DELETE", "/api/v1/workspaces/{ws}/assets/{asset_id}", None),
    ("GET", "/api/v1/workspaces/{ws}/assets/{asset_id}/timeline", None),
    # observations
    ("POST", "/api/v1/workspaces/{ws}/observations", {"asset_id": "00000000-0000-0000-0000-000000000000"}),
    ("GET", "/api/v1/workspaces/{ws}/observations", None),
    ("GET", "/api/v1/workspaces/{ws}/observations/{observation_id}", None),
    # issues
    ("GET", "/api/v1/workspaces/{ws}/issues", None),
    ("POST", "/api/v1/workspaces/{ws}/issues", {"title": "x", "asset_id": "00000000-0000-0000-0000-000000000000"}),
    ("GET", "/api/v1/workspaces/{ws}/issues/workflows", None),
    ("GET", "/api/v1/workspaces/{ws}/issues/{issue_id}", None),
    ("PATCH", "/api/v1/workspaces/{ws}/issues/{issue_id}", {"title": "x"}),
    ("POST", "/api/v1/workspaces/{ws}/issues/{issue_id}/transitions", {"to_state": "investigating"}),
    (
        "POST",
        "/api/v1/workspaces/{ws}/issues/{issue_id}/evidence",
        {"observation_id": "00000000-0000-0000-0000-000000000000"},
    ),
    # tasks
    ("GET", "/api/v1/workspaces/{ws}/tasks", None),
    ("POST", "/api/v1/workspaces/{ws}/tasks", {"title": "x"}),
    ("GET", "/api/v1/workspaces/{ws}/tasks/{task_id}", None),
    ("PATCH", "/api/v1/workspaces/{ws}/tasks/{task_id}", {"title": "x"}),
    ("POST", "/api/v1/workspaces/{ws}/tasks/{task_id}/transitions", {"to_status": "in_progress"}),
    ("GET", "/api/v1/workspaces/{ws}/dashboard", None),
    ("GET", "/api/v1/workspaces/{ws}/evidence", None),
    ("POST", "/api/v1/workspaces/{ws}/evidence", {}),
    ("GET", "/api/v1/workspaces/{ws}/evidence/{evidence_id}", None),
    ("GET", "/api/v1/workspaces/{ws}/evidence/{evidence_id}/content", None),
    ("DELETE", "/api/v1/workspaces/{ws}/evidence/{evidence_id}", None),
    ("GET", "/api/v1/workspaces/{ws}/audit", None),
    ("GET", "/api/v1/workspaces/{ws}/audit/meta", None),
    ("GET", "/api/v1/workspaces/{ws}/map/layers", None),
    ("GET", "/api/v1/workspaces/{ws}/map/layers/{layer}", None),
    # botanical operations agent
    ("GET", "/api/v1/workspaces/{ws}/agent/rules", None),
    ("POST", "/api/v1/workspaces/{ws}/agent/run", None),
    ("GET", "/api/v1/workspaces/{ws}/agent/runs", None),
    ("GET", "/api/v1/workspaces/{ws}/agent/runs/{run_id}", None),
    ("GET", "/api/v1/workspaces/{ws}/recommendations", None),
    ("POST", "/api/v1/workspaces/{ws}/recommendations/{recommendation_id}/accept", {}),
    ("POST", "/api/v1/workspaces/{ws}/recommendations/{recommendation_id}/dismiss", {"reason": "not now"}),
    # evaluation protocols (Stage D3)
    ("GET", "/api/v1/workspaces/{ws}/evaluation-protocols/template", None),
    ("GET", "/api/v1/workspaces/{ws}/evaluation-protocols", None),
    ("POST", "/api/v1/workspaces/{ws}/evaluation-protocols", {"key": "p-dis-1", "content": {}}),
    ("GET", "/api/v1/workspaces/{ws}/evaluation-protocols/{protocol_id}", None),
    (
        "POST",
        "/api/v1/workspaces/{ws}/evaluation-protocols/{protocol_id}/signoffs",
        {"role": "data_owner", "decision": "approve", "note": "a long enough note"},
    ),
    # datasets (Stage D)
    ("GET", "/api/v1/workspaces/{ws}/datasets/licence-policy", None),
    ("GET", "/api/v1/workspaces/{ws}/datasets", None),
    (
        "POST",
        "/api/v1/workspaces/{ws}/datasets",
        {"name": "x", "version": "1", "source_url": "https://x.example.org", "licence_spdx": "CC0-1.0"},
    ),
    ("GET", "/api/v1/workspaces/{ws}/datasets/{dataset_id}", None),
    ("POST", "/api/v1/workspaces/{ws}/datasets/{dataset_id}/evidence", {}),
    ("POST", "/api/v1/workspaces/{ws}/datasets/{dataset_id}/transitions", {"to_status": "under_review"}),
    ("POST", "/api/v1/workspaces/{ws}/datasets/{dataset_id}/samples", {"samples": []}),
    ("GET", "/api/v1/workspaces/{ws}/datasets/{dataset_id}/samples", None),
    ("POST", "/api/v1/workspaces/{ws}/datasets/{dataset_id}/samples/import", {"csv_text": "external_id\n"}),
    (
        "POST",
        "/api/v1/workspaces/{ws}/datasets/{dataset_id}/samples/{sample_id}/reviews",
        {"to_status": "under_review"},
    ),
    ("GET", "/api/v1/workspaces/{ws}/datasets/{dataset_id}/samples/{sample_id}/reviews", None),
    ("GET", "/api/v1/workspaces/{ws}/datasets/{dataset_id}/review-summary", None),
    ("GET", "/api/v1/workspaces/{ws}/datasets/{dataset_id}/quality", None),
    ("GET", "/api/v1/workspaces/{ws}/datasets/{dataset_id}/agreement", None),
    ("POST", "/api/v1/workspaces/{ws}/datasets/{dataset_id}/splits", {}),
    ("GET", "/api/v1/workspaces/{ws}/datasets/{dataset_id}/splits", None),
    ("GET", "/api/v1/workspaces/{ws}/datasets/{dataset_id}/splits/{version}", None),
    ("GET", "/api/v1/workspaces/{ws}/datasets/{dataset_id}/claim-readiness", None),
]


def _fill(path: str, ws: str) -> str:
    """Substitute {ws}; every other path parameter becomes a well-formed id that does not exist."""
    import re

    return re.sub(r"\{(\w+)\}", lambda m: ws if m.group(1) == "ws" else "00000000-0000-0000-0000-00000000dead", path)


def test_every_workspace_route_is_covered_by_isolation_matrix(app):
    scoped = {
        (method.upper(), path) for path, ops in app.openapi()["paths"].items() if "{ws}" in path for method in ops
    }
    assert scoped, "no workspace-scoped routes found; the matrix check would be vacuous"
    covered = {(m, p.split("?")[0]) for m, p, _ in ENDPOINTS}
    assert scoped == covered, f"uncovered workspace routes: {scoped - covered}"


@pytest.mark.parametrize("method,path,body", ENDPOINTS)
def test_non_member_gets_404_and_nothing_leaks(client, make_actor, method, path, body):
    owner, outsider = make_actor("owner@example.com", "Owner"), make_actor("out@example.com", "Outsider")
    ws = owner.create_workspace()
    url = _fill(path, ws)
    r = outsider.client.request(method, url, json=body, headers=outsider.headers)
    assert r.status_code == 404, (method, url, r.text)
    assert r.json()["code"] == "workspace_not_found"
    assert "Owner" not in r.text and "owner@example.com" not in r.text


@pytest.mark.parametrize("method,path,body", ENDPOINTS)
def test_unauthenticated_gets_401(client, make_actor, method, path, body):
    ws = make_actor("owner@example.com").create_workspace()
    r = client.request(method, _fill(path, ws), json=body)
    assert r.status_code == 401


def test_unknown_workspace_id_looks_identical_to_forbidden_one(client, make_actor):
    a = make_actor("a@example.com")
    r = a.get("/api/v1/workspaces/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404 and r.json()["code"] == "workspace_not_found"


def test_list_only_shows_own_workspaces(make_actor):
    a, b = make_actor("a@example.com"), make_actor("b@example.com")
    wa = a.create_workspace("A's farm", "agricultural_production")
    wb = b.create_workspace("B's park")
    assert [w["id"] for w in a.get("/api/v1/workspaces").json()] == [wa]
    assert [w["id"] for w in b.get("/api/v1/workspaces").json()] == [wb]


def test_workspace_creation_sets_owner_and_mode(make_actor):
    a = make_actor("a@example.com")
    r = a.post("/api/v1/workspaces", {"name": "Farm", "mode": "agricultural_production", "timezone": "Asia/Kolkata"})
    assert r.status_code == 201
    body = r.json()
    assert body["role"] == "owner" and body["mode"] == "agricultural_production" and body["timezone"] == "Asia/Kolkata"
    assert a.post("/api/v1/workspaces", {"name": "X", "mode": "bogus"}).status_code == 422
    assert (
        a.post("/api/v1/workspaces", {"name": "X", "mode": "green_management", "timezone": "Mars/Base"}).status_code
        == 422
    )


def test_roles_gate_mutations(make_actor):
    owner, viewer, worker = (
        make_actor("o@example.com"),
        make_actor("v@example.com", "V"),
        make_actor("w@example.com", "W"),
    )
    ws = owner.create_workspace()
    assert (
        owner.post(f"/api/v1/workspaces/{ws}/members", {"email": "v@example.com", "role": "viewer"}).status_code == 201
    )
    assert (
        owner.post(f"/api/v1/workspaces/{ws}/members", {"email": "w@example.com", "role": "worker"}).status_code == 201
    )
    for actor in (viewer, worker):
        assert actor.get(f"/api/v1/workspaces/{ws}").status_code == 200  # members can read
        assert actor.patch(f"/api/v1/workspaces/{ws}", {"name": "x"}).status_code == 403
        assert (
            actor.post(f"/api/v1/workspaces/{ws}/members", {"email": "o@example.com", "role": "viewer"}).status_code
            == 403
        )
    assert owner.patch(f"/api/v1/workspaces/{ws}", {"name": "Renamed"}).json()["name"] == "Renamed"


def test_owner_role_protections(make_actor):
    owner, admin = make_actor("o@example.com", "O"), make_actor("ad@example.com", "Ad")
    ws = owner.create_workspace()
    owner.post(f"/api/v1/workspaces/{ws}/members", {"email": "ad@example.com", "role": "admin"})
    # admin cannot mint owners, change the owner, or remove the owner
    assert admin.post(f"/api/v1/workspaces/{ws}/members", {"email": "o@example.com", "role": "owner"}).status_code in (
        403,
        409,
    )
    assert admin.patch(f"/api/v1/workspaces/{ws}/members/{owner.id}", {"role": "viewer"}).status_code == 403
    assert admin.delete(f"/api/v1/workspaces/{ws}/members/{owner.id}").status_code == 403
    # the last owner cannot demote or remove themselves
    assert owner.patch(f"/api/v1/workspaces/{ws}/members/{owner.id}", {"role": "admin"}).json()["code"] == "last_owner"
    assert owner.delete(f"/api/v1/workspaces/{ws}/members/{owner.id}").json()["code"] == "last_owner"


def test_member_management_happy_path_and_conflicts(make_actor):
    owner, other = make_actor("o@example.com", "O"), make_actor("x@example.com", "X")
    ws = owner.create_workspace()
    assert (
        owner.post(f"/api/v1/workspaces/{ws}/members", {"email": "ghost@example.com", "role": "worker"}).json()["code"]
        == "user_not_found"
    )
    assert (
        owner.post(f"/api/v1/workspaces/{ws}/members", {"email": "x@example.com", "role": "manager"}).status_code == 201
    )
    assert (
        owner.post(f"/api/v1/workspaces/{ws}/members", {"email": "x@example.com", "role": "manager"}).json()["code"]
        == "already_member"
    )
    assert owner.patch(f"/api/v1/workspaces/{ws}/members/{other.id}", {"role": "worker"}).json()["role"] == "worker"
    assert {m["email"] for m in owner.get(f"/api/v1/workspaces/{ws}/members").json()} == {
        "o@example.com",
        "x@example.com",
    }
    assert owner.delete(f"/api/v1/workspaces/{ws}/members/{other.id}").status_code == 204
    assert other.get(f"/api/v1/workspaces/{ws}").status_code == 404  # access ends immediately


def test_capabilities_never_claim_unbuilt_features(make_actor):
    a = make_actor("a@example.com")
    ws = a.create_workspace()
    caps = {c["key"]: c for c in a.get(f"/api/v1/workspaces/{ws}/capabilities").json()}
    for key in (
        "disease_detection",
        "crop_recommendation",
        "yield_prediction",
        "optimization",
        "irrigation_recommendation",
    ):
        assert caps[key]["available"] is False and caps[key]["reason"]
    # Genuinely implemented and wired (rule-based agent, weather context): these may be advertised as live.
    assert caps["weather_context"]["available"] is True
    assert caps["botanical_agent_rules"]["available"] is True
    assert caps["botanical_agent_rules"]["technique"] == "Rules + statistics"  # never "AI"/"ML"
