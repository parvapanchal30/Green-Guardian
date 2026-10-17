"""Audit trail: what is recorded, what is never recorded, atomicity, access control, immutability, tenant isolation."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select, text

from app.modules.audit import service as audit_service
from app.modules.audit.models import AuditEvent, AuditImmutable
from tests.conftest import requires_pg_mode
from tests.helpers import make_asset, make_issue, make_location, make_task, observe

PASSWORD = "audit-test-password-1"


def rows(world, **where) -> list[AuditEvent]:
    with world.db() as db:
        q = select(AuditEvent).order_by(AuditEvent.occurred_at, AuditEvent.id)
        for k, v in where.items():
            q = q.where(getattr(AuditEvent, k) == v)
        return list(db.scalars(q))


def actions(world, **where) -> list[str]:
    return [r.action for r in rows(world, **where)]


def listing(api, **params):
    r = api.get("/audit", params=params or None)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ authentication events


def test_registration_login_logout_are_recorded_with_actor_request_id_and_address(client, world):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "ann@example.com", "password": PASSWORD, "name": "Ann"},
        headers={"X-Request-ID": "audit-reg-000001"},
    )
    uid = uuid.UUID(r.json()["id"])
    tok = client.post(
        "/api/v1/auth/login",
        json={"email": "ann@example.com", "password": PASSWORD},
        headers={"X-Request-ID": "audit-login-00001", "User-Agent": "pytest-agent/1.0"},
    ).json()
    client.post("/api/v1/auth/logout", json={"refresh_token": tok["refresh_token"]})

    mine = rows(world, actor_id=uid)
    assert [e.action for e in mine] == ["auth.register", "auth.login.success", "auth.logout"]
    reg, login, _ = mine
    assert reg.request_id == "audit-reg-000001" and login.request_id == "audit-login-00001"
    assert login.client_ip == "testclient" and login.user_agent == "pytest-agent/1.0"
    assert all(e.target_type == "user" and e.target_id == uid and e.outcome == "success" for e in mine)
    assert all(e.workspace_id is None for e in mine)  # pre-workspace events


def test_failed_logins_are_recorded_without_the_email_or_whether_it_exists(client, world):
    client.post("/api/v1/auth/register", json={"email": "ann@example.com", "password": PASSWORD, "name": "Ann"})
    client.post("/api/v1/auth/login", json={"email": "ann@example.com", "password": "wrong-password-1"})
    client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "wrong-password-1"})
    fails = [e for e in rows(world) if e.action == "auth.login.failure"]
    assert len(fails) == 2 and all(e.outcome == "failure" and e.actor_id is None for e in fails)
    assert fails[0].details.keys() == fails[1].details.keys() == {"email_ref", "reason"}  # identical shape
    blob = json.dumps([e.details for e in fails])
    assert "ann@example.com" not in blob and "ghost@example.com" not in blob and "wrong-password" not in blob
    assert len(fails[0].details["email_ref"]) == 16


def test_a_lockout_is_recorded_once_and_blocked_attempts_do_not_flood_the_trail(client, world):
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "wrong-password-1"})
    before = len(rows(world))
    for _ in range(25):  # an attacker hammering a locked key
        assert (
            client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "x" * 12}).status_code
            == 429
        )
    assert len(rows(world)) == before  # blocked attempts write nothing
    locked = [e for e in rows(world) if e.action == "auth.login.locked"]
    assert len(locked) == 1 and locked[0].outcome == "denied" and "pair" in locked[0].details["scopes"]


def test_refresh_token_reuse_is_a_denied_security_event(client, world):
    client.post("/api/v1/auth/register", json={"email": "ann@example.com", "password": PASSWORD, "name": "Ann"})
    tok = client.post("/api/v1/auth/login", json={"email": "ann@example.com", "password": PASSWORD}).json()
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]}).status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]}).status_code == 401
    ev = next(e for e in rows(world) if e.action == "auth.refresh.reuse_detected")
    assert ev.outcome == "denied" and ev.actor_id is not None


def test_no_secret_ever_reaches_the_audit_trail(client, world, api_for, team):
    secret_password = "Sup3r-Secret-Passw0rd!"
    r = client.post(
        "/api/v1/auth/register", json={"email": "ann@example.com", "password": secret_password, "name": "Ann"}
    )
    tok = client.post("/api/v1/auth/login", json={"email": "ann@example.com", "password": secret_password}).json()
    client.post("/api/v1/auth/login", json={"email": "ann@example.com", "password": "another-Wrong-Passw0rd"})
    client.patch(
        "/api/v1/me",
        json={"phone": "+91 99999 11111", "name": "Ann B"},
        headers={"Authorization": f"Bearer {tok['access_token']}"},
    )
    api_for(team.owner).patch("", {"settings": {"agent": {"inspection_gap_days": 10}, "api_key": "sk-live-123"}})
    dump = json.dumps([[e.details, e.action, e.target_type, e.user_agent, e.client_ip] for e in rows(world)])
    for secret in (
        secret_password,
        "another-Wrong-Passw0rd",
        tok["access_token"],
        tok["refresh_token"],
        "sk-live-123",
        "99999 11111",
        "ann@example.com",
    ):
        assert secret not in dump, secret
    assert str(uuid.UUID(r.json()["id"])) in json.dumps([str(e.target_id) for e in rows(world)])  # but ids are kept


# ------------------------------------------------------------------ operational events


def test_asset_lifecycle_is_audited_with_only_the_fields_that_changed(api_for, team, world):
    w, m = api_for(team.worker), api_for(team.manager)
    asset = make_asset(w, label="Neem #1", notes="first note")
    assert m.patch(f"/assets/{asset['id']}", {"label": "Neem #1 (renamed)", "notes": "first note"}).status_code == 200
    assert m.patch(f"/assets/{asset['id']}", {"label": "Neem #1 (renamed)"}).status_code == 200  # no change: no event
    assert m.delete(f"/assets/{asset['id']}").status_code < 300
    evs = rows(world, target_id=uuid.UUID(asset["id"]))
    assert [e.action for e in evs] == ["asset.create", "asset.update", "asset.archive"]
    assert evs[0].actor_id == team.worker.id and evs[2].actor_id == team.manager.id
    assert evs[1].details == {"changes": {"label": ["Neem #1", "Neem #1 (renamed)"]}}  # notes unchanged: not listed
    assert all(e.workspace_id == uuid.UUID(team.ws) for e in evs)


def test_issue_task_and_agent_workflow_events(api_for, team, world):
    w, m = api_for(team.worker), api_for(team.manager)
    asset = make_asset(w)
    obs = observe(w, asset["id"], health_score=20)  # the critical rule fires
    rec = obs["recommendations"][0]
    acc = m.post(f"/recommendations/{rec['id']}/accept", {}).json()
    issue_id = acc["accepted_entity_id"]
    m.post(f"/issues/{issue_id}/transitions", {"to_state": "investigating"})
    m.patch(f"/issues/{issue_id}", {"severity": "critical"})
    task = make_task(m, issue_id=issue_id, assignee_id=str(team.worker.id))
    w.post(f"/tasks/{task['id']}/transitions", {"to_status": "in_progress"})
    m.patch(f"/tasks/{task['id']}", {"priority": "p1"})
    m.post("/agent/run")
    got = actions(world)
    for expected in (
        "asset.create",
        "observation.create",
        "recommendation.accept",
        "issue.transition",
        "issue.update",
        "task.create",
        "task.transition",
        "task.update",
        "agent.run",
    ):
        assert expected in got, (expected, got)
    tr = next(e for e in rows(world) if e.action == "issue.transition")
    assert tr.details["from"] == "open" and tr.details["to"] == "investigating" and tr.target_id == uuid.UUID(issue_id)
    acc_ev = next(e for e in rows(world) if e.action == "recommendation.accept")
    assert acc_ev.details["created"] == "issue" and acc_ev.details["created_id"] == issue_id
    tt = next(e for e in rows(world) if e.action == "task.transition")
    assert (tt.details["from"], tt.details["to"]) == ("todo", "in_progress") and tt.actor_id == team.worker.id


def test_dismissal_and_resolution_are_audited(api_for, team, world):
    w, m = api_for(team.worker), api_for(team.manager)
    a = make_asset(w)
    rec = observe(w, a["id"], health_score=15)["recommendations"][0]
    assert m.post(f"/recommendations/{rec['id']}/dismiss", {"reason": "already handled on site"}).status_code == 200
    issue = make_issue(w, a["id"])
    m.post(
        f"/issues/{issue['id']}/transitions",
        {"to_state": "resolved", "resolution": {"outcome": "fixed", "notes": "done"}},
    )
    d = next(e for e in rows(world) if e.action == "recommendation.dismiss")
    assert d.details["reason"] == "already handled on site"
    r = [e for e in rows(world) if e.action == "issue.transition" and e.details["to"] == "resolved"]
    assert r and r[0].details["resolution"] == "fixed"


def test_workspace_and_member_changes_are_audited_without_values(api_for, team, world):
    o = api_for(team.owner)
    assert o.patch("", {"name": "Renamed", "settings": {"agent": {"inspection_gap_days": 14}}}).status_code == 200
    assert o.post("/members", {"email": team.outsider.email, "role": "worker"}).status_code in (200, 201)
    assert o.patch(f"/members/{team.outsider.id}", {"role": "manager"}).status_code == 200
    assert o.delete(f"/members/{team.outsider.id}").status_code < 300
    got = {e.action: e for e in rows(world, workspace_id=uuid.UUID(team.ws))}
    assert got["workspace.update"].details == {"fields": ["name", "settings"]}  # names, never values
    assert got["member.add"].details == {"role": "worker"} and got["member.add"].target_id == team.outsider.id
    assert got["member.role_change"].details == {"from": "worker", "to": "manager"}
    assert got["member.remove"].details == {"role": "manager"}


def test_evidence_and_location_events(api_for, team, world, client):
    import io

    from PIL import Image

    w = api_for(team.worker)
    asset = make_asset(w)
    make_location(api_for(team.manager), "Zone A")
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (1, 2, 3)).save(buf, "PNG")
    r = client.post(
        w.url("/evidence"),
        data={"asset_id": asset["id"]},
        files={"file": ("a.png", buf.getvalue(), "image/png")},
        headers=w.headers,
    )
    assert r.status_code == 201
    assert w.delete(f"/evidence/{r.json()['id']}").status_code == 204
    up = next(e for e in rows(world) if e.action == "evidence.upload")
    assert up.details["sha256"] == r.json()["sha256"] and up.details["content_type"] == "image/png"
    assert "location.create" in actions(world) and "evidence.delete" in actions(world)


def test_a_failed_operation_leaves_no_audit_record(api_for, team, world):
    w = api_for(team.worker)
    make_asset(w, tag_code="TAG-1")
    n = len(rows(world, action="asset.create"))
    assert w.post("/assets", {"label": "dup", "kind": "tree", "tag_code": "TAG-1"}).status_code == 409
    assert w.post("/assets", {"label": "x", "kind": "tree", "location_id": str(uuid.uuid4())}).status_code == 404
    assert len(rows(world, action="asset.create")) == n  # atomic with the change: no change, no record


# ------------------------------------------------------------------ reading the trail


def test_managers_read_the_trail_newest_first_with_filters_and_actor_names(api_for, team):
    w, m = api_for(team.worker), api_for(team.manager)
    a = make_asset(w, label="A")
    make_asset(w, label="B")
    make_issue(w, a["id"])
    page = listing(m)
    assert page["total"] >= 3
    times = [e["occurred_at"] for e in page["items"]]
    assert times == sorted(times, reverse=True)
    top = page["items"][0]
    assert top["actor_name"] == "Worker" and top["actor_id"] == str(team.worker.id)

    assert {e["action"] for e in listing(m, action="asset.")["items"]} == {"asset.create"}
    assert [e["target_id"] for e in listing(m, target_id=a["id"])["items"]] == [a["id"]]
    assert listing(m, actor_id=str(team.manager.id))["total"] == 0
    only = listing(m, target_type="issue")["items"]
    assert only and all(e["target_type"] == "issue" for e in only)
    assert listing(m, limit=1)["items"] and len(listing(m, limit=1)["items"]) == 1
    assert listing(m, since="2999-01-01T00:00:00Z")["total"] == 0


def test_a_request_id_finds_the_audit_rows_it_produced(api_for, team, client):
    w, m = api_for(team.worker), api_for(team.manager)
    r = client.post(
        w.url("/assets"),
        json={"label": "Traced", "kind": "tree"},
        headers={**w.headers, "X-Request-ID": "trace-for-audit-1"},
    )
    assert r.status_code == 201
    hit = listing(m, request_id="trace-for-audit-1")
    assert [e["action"] for e in hit["items"]] == ["asset.create"]


def test_only_managers_and_owners_can_read_it(api_for, team):
    assert api_for(team.viewer).get("/audit").status_code == 403
    assert api_for(team.worker).get("/audit").status_code == 403
    assert api_for(team.manager).get("/audit").status_code == 200
    assert api_for(team.owner).get("/audit").status_code == 200
    assert api_for(team.outsider).get("/audit").status_code == 404


def test_each_workspace_sees_only_its_own_trail_and_never_pre_login_events(api_for, team):
    make_asset(api_for(team.worker), label="Ours")
    theirs = api_for(team.other_owner, team.other_ws)
    make_asset(theirs, label="Theirs")
    ours_page = listing(api_for(team.manager))
    theirs_page = listing(theirs)
    ours_ids = {e["target_id"] for e in ours_page["items"]}
    assert ours_ids.isdisjoint({e["target_id"] for e in theirs_page["items"]})
    assert all(e["action"] != "auth.login.failure" for e in ours_page["items"] + theirs_page["items"])
    assert api_for(team.manager, team.other_ws).get("/audit").status_code == 404


# ------------------------------------------------------------------ immutability


def test_there_is_no_api_to_create_change_or_delete_audit_records(api_for, team, app):
    paths = {p: set(ops) for p, ops in app.openapi()["paths"].items() if "/audit" in p}
    assert paths == {"/api/v1/workspaces/{ws}/audit": {"get"}}
    o = api_for(team.owner)
    ev_id = str(uuid.uuid4())
    for call in (
        lambda: o.post("/audit", {"action": "x"}),
        lambda: o.patch(f"/audit/{ev_id}", {"action": "x"}),
        lambda: o.delete(f"/audit/{ev_id}"),
        lambda: o.client.put(o.url("/audit"), json={}, headers=o.headers),
    ):
        assert call().status_code in (404, 405)


def test_the_orm_refuses_to_update_or_delete_an_audit_record(world, api_for, team):
    make_asset(api_for(team.worker))
    with world.db() as db:
        ev = db.scalars(select(AuditEvent)).first()
        ev.action = "tampered"
        with pytest.raises(AuditImmutable):
            db.flush()
        db.rollback()
        ev = db.scalars(select(AuditEvent)).first()
        db.delete(ev)
        with pytest.raises(AuditImmutable):
            db.flush()


@requires_pg_mode
def test_postgresql_rejects_update_and_delete_even_from_raw_sql(world, api_for, team):
    make_asset(api_for(team.worker))
    with world.db() as db:
        for stmt in ("UPDATE audit_events SET action = 'tampered'", "DELETE FROM audit_events"):
            with pytest.raises(Exception, match="append-only"), db.begin_nested():
                db.execute(text(stmt))
        assert db.scalar(select(AuditEvent.id).limit(1)) is not None


# ------------------------------------------------------------------ the scrubber


def test_scrub_drops_credentials_truncates_and_bounds_size():
    out = audit_service.scrub(
        {
            "password": "x",
            "new_password": "x",
            "access_token": "x",
            "Authorization": "Bearer x",
            "api_key": "x",
            "secret_hash": "x",
            "cookie": "x",
            "keep": "fine",
            "nested": {"token": "x", "ok": 1},
            "id": uuid.UUID(int=5),
            "list": [{"password": "x", "a": 1}],
            "long": "z" * 1000,
            "n": None,
            "b": True,
        }
    )
    assert out["keep"] == "fine" and out["nested"] == {"ok": 1} and out["list"] == [{"a": 1}]
    assert not {"password", "new_password", "access_token", "Authorization", "api_key", "secret_hash", "cookie"} & set(
        out
    )
    assert out["id"] == str(uuid.UUID(int=5)) and len(out["long"]) <= 301 and out["n"] is None and out["b"] is True
    huge = audit_service._bounded({f"k{i}": "v" * 290 for i in range(40)})
    assert huge["truncated"] is True and "k0" in huge["keys"]
    assert audit_service.changes({"a": 1, "b": 2}, {"a": 1, "b": 3}, ["a", "b"]) == {"b": [2, 3]}
