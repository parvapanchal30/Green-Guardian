"""Authorization denials (403) are audited: minimal data, deduplicated, never recursive, never able to change the answer."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from app.modules.audit import denied
from app.modules.audit.models import AuditEvent
from tests.helpers import make_asset


@pytest.fixture(autouse=True)
def _fresh_dedupe():
    denied.reset_dedupe()
    yield
    denied.reset_dedupe()


def denials(world) -> list[AuditEvent]:
    with world.db() as db:
        return list(
            db.scalars(select(AuditEvent).where(AuditEvent.action == "access.denied").order_by(AuditEvent.occurred_at))
        )


def test_a_role_denial_is_recorded_with_actor_workspace_route_and_request_id(client, api_for, team, world):
    v = api_for(team.viewer)
    r = client.post(
        v.url("/assets"),
        json={"label": "x", "kind": "tree"},
        headers={**v.headers, "X-Request-ID": "denied-trace-0001"},
    )
    assert r.status_code == 403 and r.json()["code"] == "insufficient_role"  # the answer is unchanged
    (ev,) = denials(world)
    assert ev.outcome == "denied" and ev.actor_id == team.viewer.id and ev.workspace_id == uuid.UUID(team.ws)
    assert ev.request_id == "denied-trace-0001" and ev.client_ip == "testclient"
    assert ev.details["reason"] == "insufficient_role" and ev.details["method"] == "POST"
    assert ev.details["route"] == "/api/v1/workspaces/{ws}/assets"  # the template, never the real ids


def test_nothing_sensitive_is_recorded(client, api_for, team, world):
    v = api_for(team.viewer)
    client.post(
        v.url("/assets"),
        json={"label": "TOP-SECRET-LABEL", "kind": "tree", "password": "hunter2", "token": "tok-abc"},
        headers={**v.headers, "Cookie": "session=cookie-secret", "X-Api-Key": "key-secret"},
    )
    api_for(team.worker).get("/audit", params={"request_id": "QUERY-SECRET", "target_id": str(uuid.uuid4())})
    dump = json.dumps([[e.details, e.user_agent, e.target_type] for e in denials(world)])
    for secret in ("TOP-SECRET-LABEL", "hunter2", "tok-abc", "cookie-secret", "key-secret", "QUERY-SECRET"):
        assert secret not in dump, secret
    assert str(team.ws) not in dump and "Bearer" not in dump  # the workspace id appears only in its own column


def test_legitimate_access_records_no_denials(api_for, team, world):
    make_asset(api_for(team.worker))
    assert api_for(team.manager).get("/audit").status_code == 200
    assert api_for(team.viewer).get("/assets").status_code == 200
    assert api_for(team.owner).get("/members").status_code == 200
    assert denials(world) == []


def test_repeated_identical_denials_are_recorded_once_per_window(client, api_for, team, world):
    v = api_for(team.viewer)
    for _ in range(6):
        assert client.post(v.url("/assets"), json={"label": "x", "kind": "tree"}, headers=v.headers).status_code == 403
    assert len(denials(world)) == 1  # no flooding
    client.post(v.url("/tasks"), json={"title": "x"}, headers=v.headers)  # a different route is a different event
    assert len(denials(world)) == 2
    w = api_for(team.worker)
    w.get("/audit")  # a different actor is a different event
    assert len(denials(world)) == 3


def test_with_the_window_disabled_every_denial_is_recorded(client, api_for, team, world):
    world.settings.audit_denied_dedupe_s = 0
    try:
        v = api_for(team.viewer)
        for _ in range(3):
            client.post(v.url("/assets"), json={"label": "x", "kind": "tree"}, headers=v.headers)
        assert len(denials(world)) == 3
    finally:
        world.settings.audit_denied_dedupe_s = 60


def test_service_level_denials_are_recorded_too(api_for, team, world, client):
    import io

    from PIL import Image

    # The role dependency lets any worker reach the delete route; the SERVICE then refuses a worker who is not the
    # uploader. That 403 is raised deep in the service layer and must be audited just the same.
    assert api_for(team.owner).post("/members", {"email": team.outsider.email, "role": "worker"}).status_code in (
        200,
        201,
    )
    asset = make_asset(api_for(team.worker))
    w = api_for(team.worker)
    buf = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf, "PNG")
    up = client.post(
        w.url("/evidence"),
        data={"asset_id": asset["id"]},
        files={"file": ("a.png", buf.getvalue(), "image/png")},
        headers=w.headers,
    )
    assert up.status_code == 201
    other_worker = api_for(team.outsider)
    r = other_worker.delete(f"/evidence/{up.json()['id']}")
    assert r.status_code == 403 and r.json()["code"] == "insufficient_role"
    (ev,) = denials(world)
    assert ev.actor_id == team.outsider.id and ev.details["method"] == "DELETE"
    assert ev.details["route"] == "/api/v1/workspaces/{ws}/evidence/{evidence_id}"
    assert up.json()["id"] not in json.dumps(ev.details)


def test_managers_can_see_denials_in_the_audit_page_and_others_cannot(api_for, team):
    api_for(team.viewer).post("/assets", {"label": "x", "kind": "tree"})
    seen = api_for(team.manager).get("/audit", params={"action": "access."}).json()
    assert seen["total"] == 1
    item = seen["items"][0]
    assert item["outcome"] == "denied" and item["actor_name"] == "Viewer" and item["details"]["method"] == "POST"
    assert api_for(team.viewer).get("/audit").status_code == 403
    theirs = api_for(team.other_owner, team.other_ws).get("/audit", params={"action": "access."}).json()
    assert theirs["total"] == 0  # tenant isolation: another workspace never sees these


def test_unauthenticated_and_non_member_requests_are_not_recorded_as_denials(client, api_for, team, world):
    assert client.get(f"/api/v1/workspaces/{team.ws}/assets").status_code == 401
    assert api_for(team.outsider).get("/assets").status_code == 404  # existence is hidden, not "forbidden"
    assert denials(world) == []


def test_a_failing_audit_never_changes_the_response(client, api_for, team, world, monkeypatch, capsys):
    def boom(*_a, **_k):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(denied.service, "record", boom)
    v = api_for(team.viewer)
    r = client.post(v.url("/assets"), json={"label": "x", "kind": "tree"}, headers=v.headers)
    assert r.status_code == 403 and r.json()["code"] == "insufficient_role" and r.json()["request_id"]
    assert "access_denied_audit_failed" in capsys.readouterr().out  # logged, not raised
    assert denials(world) == []


def test_a_denial_inside_the_recorder_cannot_recurse(client, api_for, team, world, monkeypatch):
    from app.core.errors import Forbidden

    calls = {"n": 0}

    def recursive(*_a, **_k):
        calls["n"] += 1
        raise Forbidden("nested", code="nested")

    monkeypatch.setattr(denied.service, "record", recursive)
    v = api_for(team.viewer)
    assert client.post(v.url("/assets"), json={"label": "x", "kind": "tree"}, headers=v.headers).status_code == 403
    assert calls["n"] == 1  # one attempt, no loop


def test_the_route_template_masks_ids_when_no_route_matched():
    class FakeReq:
        scope: dict = {}

        class url:  # noqa: N801
            path = "/api/v1/workspaces/01a14905-1d23-7bbd-afcb-4eb0146770fa/things"

    assert denied.route_template(FakeReq()) == "/api/v1/workspaces/{id}/things"
