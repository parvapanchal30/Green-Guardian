"""The example-data command: loads the demo content under an EXISTING account, once, after confirmation, never in
production, creating no other accounts. Runs against the test database through injected settings, sessions and client
(it never reads backend/.env here)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import User
from app.tools import example_data


def run(world, *args, answer="yes", settings=None):
    return example_data.main(
        list(args),
        confirm=lambda _prompt: answer,
        settings=settings or world.settings,
        sessions=world.maker,
        client=TestClient(world.app),
    )


def test_loads_two_example_workspaces_owned_by_the_account(world, team, api_for, capsys):
    with world.db() as db:
        users_before = db.scalar(select(func.count()).select_from(User))
    assert run(world, "--email", team.manager.email) == 0
    m = api_for(team.manager)
    mine = {w["name"]: w for w in m.client.get("/api/v1/workspaces", headers=m.headers).json()}
    campus, farm = mine["Riverside Campus Green Cover (example)"], mine["Green Valley Farm (example)"]
    assert campus["role"] == farm["role"] == "owner"
    camp = api_for(team.manager, campus["id"])
    assert camp.get("/assets", params={"limit": 50}).json()["total"] == 7  # the same seven trees as the demo campus
    assert len(camp.get("/schedules").json()) == 1
    members = camp.get("/members").json()
    assert [mm["email"] for mm in members] == [team.manager.email]  # nobody else was added
    with world.db() as db:
        assert db.scalar(select(func.count()).select_from(User)) == users_before  # no accounts created
    assert "Done." in capsys.readouterr().out


def test_runs_only_once_per_account(world, team):
    assert run(world, "--email", team.manager.email) == 0
    assert run(world, "--email", team.manager.email) == 2


def test_refuses_unknown_accounts_production_and_a_missing_yes(world, team, capsys):
    assert run(world, "--email", "nobody@example.com") == 2
    assert "register it on the sign-in page first" in capsys.readouterr().out
    assert (
        run(world, "--email", team.manager.email, settings=world.settings.model_copy(update={"env": "production"})) == 2
    )
    assert run(world, "--email", team.manager.email, answer="no") == 1
    out = capsys.readouterr().out
    assert (
        "cancelled; nothing was written" in out and "@" not in out.split("database at")[1].split(".")[0]
    )  # no credentials shown
