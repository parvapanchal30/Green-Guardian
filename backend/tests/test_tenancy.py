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
]


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
    url = path.format(ws=ws, user_id=owner.id)
    r = outsider.client.request(method, url, json=body, headers=outsider.headers)
    assert r.status_code == 404, (method, url, r.text)
    assert r.json()["code"] == "workspace_not_found"
    assert "Owner" not in r.text and "owner@example.com" not in r.text


@pytest.mark.parametrize("method,path,body", ENDPOINTS)
def test_unauthenticated_gets_401(client, make_actor, method, path, body):
    ws = make_actor("owner@example.com").create_workspace()
    r = client.request(method, path.format(ws=ws, user_id="00000000-0000-0000-0000-000000000000"), json=body)
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
        "botanical_agent_rules",
    ):
        assert caps[key]["available"] is False and caps[key]["reason"]
    assert caps["weather_context"]["available"] is True
