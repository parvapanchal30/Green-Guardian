"""The Botanical Operations Agent (MVP): deterministic rules -> explainable recommendations -> a person decides.

Nothing here is machine learning or a language model, and the tests assert that the API says so.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import update

from app.modules.assets.models import BiologicalAsset
from app.modules.intelligence.models import Recommendation
from tests.helpers import make_asset, observe


def age_asset(world, asset_id: str, days: int) -> None:
    """Pretend the asset was registered `days` ago (fixture data, not an API capability)."""
    with world.db() as db:
        db.execute(
            update(BiologicalAsset)
            .where(BiologicalAsset.id == UUID(asset_id))
            .values(created_at=datetime.now(UTC) - timedelta(days=days))
        )
        db.commit()


def recs(api, **params):
    r = api.get("/recommendations", params=params)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_a_critical_observation_triggers_an_explained_recommendation_immediately(api_for, team):
    worker = api_for(team.worker)
    a = make_asset(worker, label="Neem #482")
    out = observe(worker, a["id"], health_score=22, symptoms=["leaf_yellowing"])
    assert [r["rule_key"] for r in out["recommendations"]] == ["critical_health"]
    rec = out["recommendations"][0]
    assert rec["method"] == "rule" and rec["severity"] == "high" and rec["status"] == "open"  # 22 is not < 40/2
    assert "Neem #482" in rec["title"] and "22" in rec["title"]
    assert "below the critical threshold 40" in rec["explanation"] and "no open issue" in rec["explanation"]
    assert rec["proposed_action"]["create"] == "issue"
    assert rec["proposed_action"]["observation_id"] == out["observation"]["id"]
    assert recs(worker)[0]["id"] == rec["id"]


def test_a_healthy_observation_recommends_nothing(api_for, team):
    worker = api_for(team.worker)
    a = make_asset(worker)
    assert observe(worker, a["id"], health_score=88)["recommendations"] == []
    assert recs(worker) == []


def test_accepting_a_recommendation_opens_a_botanical_issue_with_evidence(api_for, team):
    worker, manager = api_for(team.worker), api_for(team.manager)
    a = make_asset(worker, label="Neem #482")
    out = observe(worker, a["id"], health_score=30)
    rec = out["recommendations"][0]
    r = manager.post(f"/recommendations/{rec['id']}/accept", {"assignee_id": str(team.worker.id), "severity": "high"})
    assert r.status_code == 200, r.text
    accepted = r.json()
    assert accepted["status"] == "accepted" and accepted["accepted_entity_type"] == "issue"

    issue = manager.get(f"/issues/{accepted['accepted_entity_id']}").json()
    assert issue["source"] == "agent" and issue["recommendation_id"] == rec["id"]
    assert issue["severity"] == "high" and issue["assignee_id"] == str(team.worker.id)  # the person's choices win
    assert issue["category"] == "growth_anomaly" and issue["state"] == "open"
    assert [e["id"] for e in issue["evidence"]] == [out["observation"]["id"]]
    assert recs(manager) == []  # no longer open

    again = manager.post(f"/recommendations/{rec['id']}/accept", {})
    assert again.status_code == 409 and again.json()["code"] == "recommendation_not_open"
    # the asset now has an open issue, so the agent does not propose another one
    assert recs(manager, status="open") == []
    assert manager.post("/agent/run").json()["created"] == []


def test_dismissing_needs_a_reason_and_suppresses_repeats_for_a_while(api_for, team, world):
    worker, manager = api_for(team.worker), api_for(team.manager)
    a = make_asset(worker)
    rec = observe(worker, a["id"], health_score=25)["recommendations"][0]
    assert manager.post(f"/recommendations/{rec['id']}/dismiss", {"reason": "x"}).status_code == 422  # too short
    r = manager.post(f"/recommendations/{rec['id']}/dismiss", {"reason": "Tree is being removed next week"})
    assert r.status_code == 200 and r.json()["status"] == "dismissed"
    assert r.json()["dismissed_reason"] == "Tree is being removed next week"
    assert manager.post(f"/recommendations/{rec['id']}/dismiss", {"reason": "again please"}).status_code == 409

    assert manager.post("/agent/run").json()["created"] == []  # suppressed: it was dismissed moments ago
    assert recs(manager) == []

    with world.db() as db:  # eight days later the suppression window (7 days) has passed
        db.execute(
            update(Recommendation)
            .where(Recommendation.id == UUID(rec["id"]))
            .values(decided_at=datetime.now(UTC) - timedelta(days=8))
        )
        db.commit()
    again = manager.post("/agent/run").json()["created"]
    assert [x["rule_key"] for x in again] == ["critical_health"] and again[0]["id"] != rec["id"]


def test_running_the_agent_is_idempotent_and_never_duplicates_open_recommendations(api_for, team):
    manager = api_for(team.manager)
    a = make_asset(manager)
    observe(manager, a["id"], health_score=10)
    first = manager.post("/agent/run").json()
    second = manager.post("/agent/run").json()
    assert first["created"] == [] and second["created"] == []  # already open from the observation itself
    assert first["evaluated_assets"] == 1 and len(recs(manager)) == 1


def test_inspection_gap_recommends_an_inspection_task_and_respects_new_assets(api_for, team, world):
    manager = api_for(team.manager)
    fresh = make_asset(manager, label="Just planted")
    old = make_asset(manager, label="Neglected tree")
    age_asset(world, old["id"], 40)
    run = manager.post("/agent/run").json()
    assert [(r["rule_key"], r["title"].split(" has ")[0]) for r in run["created"]] == [
        ("inspection_gap", "Neglected tree")
    ]
    assert "Just planted" not in str(run["created"]) and fresh["id"] != old["id"]
    rec = run["created"][0]
    assert rec["method"] == "rule" and rec["proposed_action"] == {
        "create": "task",
        "type": "inspect",
        "asset_id": old["id"],
    }

    r = manager.post(f"/recommendations/{rec['id']}/accept", {"assignee_id": str(team.worker.id)})
    assert r.status_code == 200 and r.json()["accepted_entity_type"] == "task"
    task = manager.get(f"/tasks/{r.json()['accepted_entity_id']}").json()
    assert task["type"] == "inspect" and task["source"] == "agent" and task["asset_id"] == old["id"]
    assert task["assignee_id"] == str(team.worker.id) and task["due_at"] is not None and task["priority"] == "p2"
    assert manager.post("/agent/run").json()["created"] == []  # an open inspection task already exists


def test_an_observation_resets_the_inspection_clock(api_for, team, world):
    manager = api_for(team.manager)
    a = make_asset(manager)
    age_asset(world, a["id"], 40)
    observe(manager, a["id"], health_score=90)  # inspected today
    assert manager.post("/agent/run").json()["created"] == []


def test_a_fast_health_decline_is_flagged_as_statistical_not_critical(api_for, team):
    worker = api_for(team.worker)
    a = make_asset(worker)
    from tests.helpers import ago

    observe(worker, a["id"], health_score=88, observed_at=ago(days=8))
    out = observe(worker, a["id"], health_score=62, observed_at=ago(days=1))
    assert [(r["rule_key"], r["method"]) for r in out["recommendations"]] == [("health_decline", "statistical")]
    assert "88 -> 62" in out["recommendations"][0]["explanation"]


def test_only_one_issue_is_proposed_per_asset_even_if_several_rules_fire(api_for, team):
    worker = api_for(team.worker)
    from tests.helpers import ago

    a = make_asset(worker)
    observe(worker, a["id"], health_score=90, observed_at=ago(days=5))
    out = observe(worker, a["id"], health_score=15)  # both "critical" and "declined by 75 points"
    assert [r["rule_key"] for r in out["recommendations"]] == ["critical_health"]


def test_thresholds_come_from_workspace_settings(api_for, team):
    owner = api_for(team.owner)
    a = make_asset(owner)
    assert observe(owner, a["id"], health_score=55)["recommendations"] == []  # default threshold is 40
    r = owner.patch("", {"settings": {"agent": {"critical_health_below": 60}}})
    assert r.status_code == 200, r.text
    assert [x["rule_key"] for x in observe(owner, a["id"], health_score=55)["recommendations"]] == ["critical_health"]
    # a malformed override cannot break the agent: it falls back to the default
    owner.patch("", {"settings": {"agent": {"critical_health_below": "banana", "inspection_gap_days": -5}}})
    rules = {r["key"]: r for r in owner.get("/agent/rules").json()}
    assert rules["critical_health"]["parameters"]["critical_health_below"] == 40.0
    assert rules["inspection_gap"]["parameters"]["inspection_gap_days"] == 21


def test_the_api_is_honest_about_what_the_agent_is(api_for, team):
    viewer = api_for(team.viewer)
    rules = viewer.get("/agent/rules").json()
    assert {r["key"] for r in rules} == {"critical_health", "health_decline", "inspection_gap"}
    assert {r["method"] for r in rules} <= {"rule", "statistical"}  # never "model" or "llm"
    run = api_for(team.manager).post("/agent/run").json()
    assert "No machine-learning or language-model output" in run["note"]
    caps = {
        c["key"]: c
        for c in viewer.client.get(f"/api/v1/workspaces/{team.ws}/capabilities", headers=viewer.headers).json()
    }
    assert caps["botanical_agent_rules"]["technique"] == "Rules + statistics"
    assert caps["disease_detection"]["available"] is False  # future capabilities are not claimed


def test_roles_and_tenancy_for_recommendations(api_for, team):
    worker, manager, viewer = api_for(team.worker), api_for(team.manager), api_for(team.viewer)
    a = make_asset(worker)
    rec = observe(worker, a["id"], health_score=5)["recommendations"][0]  # field staff trigger it...
    assert viewer.get("/recommendations").json()["total"] == 1  # ...everyone can read it...
    for who in (worker, viewer):  # ...but only managers decide
        assert who.post(f"/recommendations/{rec['id']}/accept", {}).status_code == 403
        assert who.post(f"/recommendations/{rec['id']}/dismiss", {"reason": "nope nope"}).status_code == 403
        assert who.post("/agent/run").status_code == 403
    other = api_for(team.other_owner, team.other_ws)
    assert other.get("/recommendations").json()["total"] == 0
    assert other.post(f"/recommendations/{rec['id']}/accept", {}).status_code == 404
    assert manager.post("/recommendations/00000000-0000-0000-0000-00000000beef/accept", {}).status_code == 404
    assert manager.post(f"/recommendations/{rec['id']}/accept", {"severity": "apocalyptic"}).status_code == 422


def test_an_issue_resolved_with_the_asset_still_critical_can_be_flagged_again(api_for, team):
    manager, worker = api_for(team.manager), api_for(team.worker)
    a = make_asset(worker)
    first = observe(worker, a["id"], health_score=20)["recommendations"][0]
    accepted = manager.post(f"/recommendations/{first['id']}/accept", {}).json()
    manager.post(
        f"/issues/{accepted['accepted_entity_id']}/transitions",
        {"to_state": "resolved", "resolution": {"outcome": "mitigated", "notes": "n"}},
    )
    run = manager.post("/agent/run").json()
    assert any(r["rule_key"] == "critical_health" for r in run["created"])  # the score never recovered: say so
