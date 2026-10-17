"""Request correlation IDs: header, error bodies, structured logs, malformed input, thread propagation, client IP."""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.core.request_context import (
    accept_or_generate,
    client_ip_from_scope,
    current_client_ip,
    current_request_id,
)

HEX32 = re.compile(r"^[0-9a-f]{32}$")


@pytest.fixture
def probe(app):
    """A client for the app plus probe routes that read the context from inside synchronous handlers."""

    @app.get("/__ctx")
    def ctx():  # sync handler: runs in a worker thread, like every real handler
        return {"request_id": current_request_id(), "ip": current_client_ip()}

    @app.get("/__boom")
    def boom():
        raise RuntimeError("secret internal detail: db password is hunter2")

    return TestClient(app, raise_server_exceptions=False)


def test_every_response_carries_a_unique_request_id(client):
    ids = {client.get("/healthz").headers["x-request-id"] for _ in range(5)}
    assert len(ids) == 5 and all(HEX32.match(i) for i in ids)


def test_a_valid_incoming_id_is_kept(client):
    r = client.get("/healthz", headers={"X-Request-ID": "client-trace-12345"})
    assert r.headers["x-request-id"] == "client-trace-12345"


@pytest.mark.parametrize(
    "bad",
    [
        "short",
        "has spaces in it!!",
        "x" * 65,
        "bad<script>alert(1)</script>",
        "-startswithdash",
        "emoji-é-id-1234",
        "a" * 8 + "\x7f",
    ],
)
def test_malformed_incoming_ids_are_replaced_never_echoed(client, bad):
    try:
        r = client.get("/healthz", headers={"X-Request-ID": bad})
    except Exception:  # some values cannot even be sent as a header; that is also a safe outcome
        return
    got = r.headers["x-request-id"]
    assert got != bad and HEX32.match(got)


def test_accept_or_generate_unit():
    assert accept_or_generate("abc12345") == "abc12345"
    assert accept_or_generate("a.b_c-d:e1234") == "a.b_c-d:e1234"
    for bad in (None, "", "short", "x" * 65, "has space 1234", "line\nbreak1234"):
        assert HEX32.match(accept_or_generate(bad))


def test_error_bodies_carry_the_same_id_as_the_header(client, team):
    for r in (
        client.get("/api/v1/me"),  # 401
        client.post("/api/v1/auth/login", json={"email": "not-an-email"}),  # 422
        client.get("/api/v1/nope"),  # 404
    ):
        body = r.json()
        assert r.status_code >= 400
        assert body["request_id"] == r.headers["x-request-id"]
    r = client.get("/api/v1/me", headers={"X-Request-ID": "trace-from-client-1"})
    assert r.json()["request_id"] == "trace-from-client-1"


def test_unhandled_errors_get_a_generic_body_with_the_id_and_no_internals(probe, capsys):
    r = probe.get("/__boom", headers={"X-Request-ID": "boom-trace-0001"})
    assert r.status_code == 500
    assert r.headers["x-request-id"] == "boom-trace-0001"
    body = r.json()
    assert body["code"] == "internal_error" and body["request_id"] == "boom-trace-0001"
    assert "hunter2" not in r.text and "RuntimeError" not in r.text
    logged = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    err = next(e for e in logged if e["event"] == "unhandled_exception")
    assert err["request_id"] == "boom-trace-0001" and err["error_type"] == "RuntimeError"
    assert "hunter2" in err["exception"]  # the traceback is in the server log, never in the response


def test_the_id_reaches_synchronous_handler_threads(probe):
    r = probe.get("/__ctx", headers={"X-Request-ID": "thread-trace-0001"})
    assert r.json()["request_id"] == "thread-trace-0001"
    assert current_request_id() is None  # and nothing leaks out of the request afterwards


def test_each_request_is_logged_with_its_id(probe, capsys):
    r = probe.get("/__ctx", headers={"X-Request-ID": "log-trace-000001"})
    logged = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    access = [e for e in logged if e["event"] == "request" and e["path"] == "/__ctx"]
    assert len(access) == 1
    assert access[0]["request_id"] == "log-trace-000001" and access[0]["status"] == r.status_code == 200
    assert access[0]["method"] == "GET" and access[0]["duration_ms"] >= 0


def test_ids_do_not_bleed_between_requests(probe, capsys):
    probe.get("/__ctx", headers={"X-Request-ID": "first-trace-00001"})
    probe.get("/__ctx", headers={"X-Request-ID": "second-trace-0001"})
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    ids = [e["request_id"] for e in lines if e["event"] == "request" and e["path"] == "/__ctx"]
    assert ids == ["first-trace-00001", "second-trace-0001"]


def test_cors_exposes_the_request_id_header_to_the_browser(client):
    r = client.get("/healthz", headers={"Origin": "http://localhost:5173"})
    assert "x-request-id" in r.headers["access-control-expose-headers"].lower()


# ------------------------------------------------------------------ client address


def scope(peer, xff=None):
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return {"client": (peer, 5555), "headers": headers}


def test_client_ip_ignores_forwarded_headers_unless_proxies_are_trusted():
    s = scope("10.0.0.9", "6.6.6.6, 1.2.3.4")
    assert client_ip_from_scope(s, 0) == "10.0.0.9"  # a spoofed header changes nothing by default


def test_client_ip_takes_the_nth_entry_from_the_right_when_proxies_are_trusted():
    s = scope("10.0.0.9", "6.6.6.6, 1.2.3.4, 9.9.9.9")
    assert client_ip_from_scope(s, 1) == "9.9.9.9"
    assert client_ip_from_scope(s, 2) == "1.2.3.4"  # 6.6.6.6 (client-controlled) is never reached with 2 trusted hops
    assert client_ip_from_scope(s, 3) == "6.6.6.6"
    assert client_ip_from_scope(s, 4) == "10.0.0.9"  # fewer hops than expected: fall back to the peer
    assert client_ip_from_scope(scope(None), 0) is None


def test_the_client_ip_is_available_inside_handlers(probe):
    assert probe.get("/__ctx").json()["ip"] == "testclient"
    spoofed = probe.get("/__ctx", headers={"X-Forwarded-For": "6.6.6.6"})
    assert spoofed.json()["ip"] == "testclient"  # default config: header ignored
