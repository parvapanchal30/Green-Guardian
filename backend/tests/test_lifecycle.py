"""Start-up and shutdown behaviour of the API process (health endpoints and graceful release of database connections)."""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main


def test_health_endpoints(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}


def test_graceful_shutdown_releases_database_connections(world, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(main, "dispose_engine", lambda: calls.append("disposed"))
    with TestClient(world.app) as c:  # entering runs start-up, leaving runs shutdown
        assert c.get("/healthz").status_code == 200
        assert calls == []  # nothing is released while serving
    assert calls == ["disposed"]
