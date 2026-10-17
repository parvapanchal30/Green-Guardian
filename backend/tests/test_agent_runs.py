"""Agent run lifecycle: history, overlap prevention, failure handling, abandoned runs, tenant isolation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.modules.intelligence import runner, runs
from app.modules.intelligence.models import AgentRun, Recommendation, RunStatus, RunTrigger
from tests.helpers import make_asset, observe
from tests.test_agent_api import age_asset


def _ws(team):
    return uuid.UUID(team.ws)


def _ws_other(team):
    return uuid.UUID(team.other_ws)


def history(api, **params):
    r = api.get("/agent/runs", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_manual_run_is_recorded_with_its_rules_versions_and_counts(api_for, team):
    manager = api_for(team.manager)
    make_asset(manager, label="A")
    out = manager.post("/agent/run").json()
    run = out["run"]
    assert run["trigger"] == "manual" and run["status"] == "succeeded" and run["error"] is None
    assert run["requested_by"] == str(team.manager.id)
    assert run["evaluated_assets"] == 1 == out["evaluated_assets"]
    assert run["finished_at"] is not None and run["duration_s"] is not None and run["duration_s"] >= 0
    by_key = {r["key"]: r for r in run["rules"]}
    assert by_key["inspection_gap"]["version"] == 2 and by_key["critical_health"]["version"] == 1
    assert by_key["inspection_gap"]["parameters"] == {"inspection_gap_days": 21}
    assert "weather" in run["diagnostics"] and "skipped" in run["diagnostics"]

    listed = history(manager)
    assert listed["total"] == 1 and listed["items"][0]["id"] == run["id"]
    assert manager.get(f"/agent/runs/{run['id']}").json()["id"] == run["id"]


def test_history_is_newest_first_and_paginated(api_for, team):
    manager = api_for(team.manager)
    ids = [manager.post("/agent/run").json()["run"]["id"] for _ in range(3)]
    page = history(manager, limit=2)
    assert page["total"] == 3 and [r["id"] for r in page["items"]] == [ids[2], ids[1]]
    assert [r["id"] for r in history(manager, limit=2, offset=2)["items"]] == [ids[0]]


def test_history_is_visible_to_viewers_but_running_the_agent_is_not(api_for, team):
    api_for(team.manager).post("/agent/run")
    viewer, worker = api_for(team.viewer), api_for(team.worker)
    assert viewer.get("/agent/runs").status_code == 200
    assert viewer.post("/agent/run").status_code == 403
    assert worker.post("/agent/run").status_code == 403


def test_runs_of_another_workspace_are_invisible(api_for, team):
    mine = api_for(team.manager)
    run_id = mine.post("/agent/run").json()["run"]["id"]
    theirs = api_for(team.other_owner, team.other_ws)
    assert theirs.get("/agent/runs").json()["total"] == 0
    r = theirs.get(f"/agent/runs/{run_id}")
    assert r.status_code == 404 and r.json()["code"] == "agent_run_not_found"
    # and the other workspace's own run history is separate
    theirs.post("/agent/run")
    assert mine.get("/agent/runs").json()["total"] == 1 and theirs.get("/agent/runs").json()["total"] == 1


def test_a_second_run_while_one_is_in_progress_is_refused(api_for, team, world):
    manager = api_for(team.manager)
    with world.db() as db:
        db.add(AgentRun(workspace_id=_ws(team), trigger="scheduled", status="running", started_at=datetime.now(UTC)))
        db.commit()
    r = manager.post("/agent/run")
    assert r.status_code == 409 and r.json()["code"] == "agent_run_in_progress"
    assert history(manager)["total"] == 1  # the refused attempt left no row behind


def test_the_database_itself_allows_only_one_running_row_per_workspace(world, team):
    ws = uuid.UUID(team.ws)
    with world.db() as db:
        first = runs.claim(db, ws, RunTrigger.SCHEDULED, worker_id="w1")
        second = runs.claim(db, ws, RunTrigger.MANUAL)
        assert first is not None and second is None
        assert db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.status == "running")) == 1
        # a different workspace is independent
        other = runs.claim(db, uuid.UUID(team.other_ws), RunTrigger.SCHEDULED, worker_id="w1")
        assert other is not None
        # once finished, the workspace can run again
        first.status = RunStatus.SUCCEEDED.value
        db.commit()
        assert runs.claim(db, ws, RunTrigger.SCHEDULED, worker_id="w2") is not None


def test_a_failing_evaluation_is_recorded_and_leaves_nothing_half_applied(api_for, team, world, monkeypatch):
    manager = api_for(team.manager)
    a = make_asset(manager, label="Sick tree")
    observe(manager, a["id"], health_score=15)
    stale = make_asset(manager, label="Neglected tree")
    age_asset(world, stale["id"], 40)  # the failing run WOULD create an inspection advice for this one
    before = len(manager.get("/recommendations").json()["items"])
    assert before == 1

    real = runner._persist

    def boom(db, workspace_id, findings, cfg, now, run_id=None):
        real(db, workspace_id, findings, cfg, now, run_id)  # do real work first ...
        raise RuntimeError("provider exploded with secret=hunter2")  # ... then fail mid-run

    monkeypatch.setattr(runner, "_persist", boom)
    r = manager.post("/agent/run")
    assert r.status_code == 500 and r.json()["code"] == "agent_run_failed"
    monkeypatch.undo()

    failed = history(manager)["items"][0]
    assert failed["status"] == "failed" and failed["finished_at"] is not None
    assert failed["error"].startswith("RuntimeError") and failed["recommendations_created"] == 0
    assert "hunter2" not in failed["error"] and "[redacted]" in failed["error"]  # no secret reaches the history
    assert "hunter2" not in r.text
    assert len(manager.get("/recommendations").json()["items"]) == before  # nothing half-applied
    assert manager.post("/agent/run").json()["run"]["recommendations_created"] == 1  # it is created by a good run
    # the failure is audited, and the workspace is not stuck
    audit = api_for(team.owner).get("/audit", params={"action": "agent.run"}).json()["items"]
    assert any(e["outcome"] == "failure" and e["details"].get("error_type") == "RuntimeError" for e in audit)
    assert manager.post("/agent/run").json()["run"]["status"] == "succeeded"


def test_abandoned_runs_are_failed_after_the_timeout_and_unblock_the_workspace(api_for, team, world):
    manager = api_for(team.manager)
    now = datetime.now(UTC)
    with world.db() as db:
        db.add(
            AgentRun(workspace_id=_ws(team), trigger="scheduled", status="running", started_at=now - timedelta(hours=2))
        )
        db.add(
            AgentRun(
                workspace_id=_ws_other(team),
                trigger="scheduled",
                status="running",
                started_at=now - timedelta(minutes=1),
            )
        )
        db.commit()
        assert runs.reap_stale(db, stale_after_s=1800, now=now) == 1  # only the old one
    items = history(manager)["items"]
    assert items[0]["status"] == "failed" and "abandoned" in items[0]["error"]
    assert manager.post("/agent/run").json()["run"]["status"] == "succeeded"
    with world.db() as db:  # the other workspace's recent run is untouched
        other = db.scalar(select(AgentRun).where(AgentRun.workspace_id == _ws_other(team)))
        assert other is not None and other.status == "running"


def test_recommendations_carry_the_run_and_rule_version_that_produced_them(api_for, team):
    manager = api_for(team.manager)
    a = make_asset(manager, label="Observed")
    observe(manager, a["id"], health_score=12)  # evaluated inline on save: no run
    inline = manager.get("/recommendations").json()["items"][0]
    assert inline["agent_run_id"] is None and inline["rule_version"] == 1 and inline["outcome"] is None


def test_scheduled_and_manual_runs_never_overlap_even_if_claimed_back_to_back(world, team):
    ws = uuid.UUID(team.ws)
    with world.db() as db:
        got = [runs.claim(db, ws, RunTrigger.SCHEDULED, worker_id=f"w{i}") for i in range(4)]
    assert sum(g is not None for g in got) == 1


@pytest.mark.parametrize("path", ["/agent/runs", "/agent/runs/00000000-0000-0000-0000-00000000dead"])
def test_run_history_requires_membership(client, team, path):
    r = client.get(f"/api/v1/workspaces/{team.ws}{path}")
    assert r.status_code == 401


def test_run_counts_in_the_database_match_the_history(api_for, team, world):
    manager = api_for(team.manager)
    manager.post("/agent/run")
    manager.post("/agent/run")
    with world.db() as db:
        assert db.scalar(select(func.count()).select_from(AgentRun)) == 2
        assert db.scalar(select(func.count()).select_from(Recommendation)) == 0
