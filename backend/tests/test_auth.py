from __future__ import annotations

from app.core.config import Settings
from tests.conftest import PASSWORD


def test_register_normalizes_email_and_rejects_duplicates(client):
    r = client.post("/api/v1/auth/register", json={"email": "Ana@Example.com", "password": PASSWORD, "name": "Ana"})
    assert r.status_code == 201 and r.json()["email"] == "ana@example.com"
    assert "password" not in r.text
    dup = client.post("/api/v1/auth/register", json={"email": "ana@example.COM", "password": PASSWORD, "name": "x"})
    assert dup.status_code == 409 and dup.json()["code"] == "email_taken"
    assert dup.headers["content-type"].startswith("application/problem+json")


def test_register_validation_problem_details(client):
    r = client.post("/api/v1/auth/register", json={"email": "not-an-email", "password": "short", "name": ""})
    assert r.status_code == 422 and r.json()["code"] == "validation_error"
    assert {e["loc"][-1] for e in r.json()["errors"]} >= {"email", "password", "name"}


def test_login_failures_are_indistinguishable(client, make_actor):
    make_actor("a@example.com")
    wrong_pw = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "nope-nope-nope"})
    unknown = client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope-nope-nope"})
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json()["code"] == unknown.json()["code"] == "invalid_credentials"
    assert wrong_pw.json()["detail"] == unknown.json()["detail"]


def test_me_requires_valid_token(client, make_actor):
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer garbage"}).json()["code"] == "invalid_token"
    a = make_actor("a@example.com", "Ana")
    r = a.get("/api/v1/me")
    assert r.status_code == 200 and r.json()["name"] == "Ana"
    r = a.patch("/api/v1/me", {"name": "Ana B", "phone": "+91 99999 00000"})
    assert r.json()["name"] == "Ana B" and r.json()["phone"] == "+91 99999 00000"


def test_expired_access_token_rejected(app, client, make_actor):
    a = make_actor("a@example.com")
    from app.core.config import get_settings
    from app.core.security import create_access_token

    s: Settings = app.dependency_overrides[get_settings]()
    expired, _ = create_access_token(
        __import__("uuid").UUID(a.id), s.model_copy(update={"access_token_ttl_minutes": -5})
    )
    r = client.get("/api/v1/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401 and r.json()["code"] == "token_expired"


def test_refresh_rotates_and_reuse_revokes_all_sessions(client, make_actor):
    a = make_actor("a@example.com")
    old = a.tokens["refresh_token"]
    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": old})
    assert r1.status_code == 200
    new = r1.json()["refresh_token"]
    assert new != old
    # replaying the rotated token is treated as theft: it fails AND kills the new session too
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": old})
    assert replay.status_code == 401 and replay.json()["code"] == "refresh_token_reuse"
    after = client.post("/api/v1/auth/refresh", json={"refresh_token": new})
    assert after.status_code == 401


def test_logout_revokes_refresh_token(client, make_actor):
    a = make_actor("a@example.com")
    rt = a.tokens["refresh_token"]
    assert client.post("/api/v1/auth/logout", json={"refresh_token": rt}).status_code == 204
    assert client.post("/api/v1/auth/logout", json={"refresh_token": rt}).status_code == 204  # idempotent
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": rt}).status_code == 401
