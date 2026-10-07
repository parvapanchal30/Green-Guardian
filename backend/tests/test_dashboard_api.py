"""Dashboard read model: figures are aggregated in the database, filters scope everything, one shape for both modes."""

from __future__ import annotations

from sqlalchemy import event

from tests.helpers import ago, ahead, make_asset, make_issue, make_location, make_task, observe, resolve_body


def dash(api, **params):
    r = api.get("/dashboard", params=params or None)
    assert r.status_code == 200, r.text
    return r.json()


def test_empty_workspace_is_all_zeros(api_for, team):
    d = dash(api_for(team.manager))
    assert d["assets"]["total"] == 0 and d["assets"]["health"] == {
        "healthy": 0,
        "at_risk": 0,
        "critical": 0,
        "unknown": 0,
    }
    w = d["work"]
    assert (w["open_issues"], w["open_tasks"], w["overdue_tasks"], w["inspections_due"]) == (0, 0, 0, 0)
    assert d["recent_activity"] == []
    assert all(not k["available"] for k in d["kpis"] if k["key"] == "health")  # nothing to compute from


def test_health_bands_and_unknown_are_counted_separately(api_for, team):
    api = api_for(team.worker)
    for label, score in (("a", 90), ("b", 85), ("c", 55), ("d", 20)):
        observe(api, make_asset(api, label=label)["id"], health_score=score)
    make_asset(api, label="never observed")
    gone = make_asset(api, label="archived")
    assert api_for(team.manager).delete(f"/assets/{gone['id']}").status_code < 300

    d = dash(api)
    assert d["assets"]["total"] == 5  # archived excluded
    h = d["assets"]["health"]
    assert h["healthy"] == 2 and h["at_risk"] == 1 and h["critical"] == 1 and h["unknown"] == 1
    assert d["assets"]["by_kind"] == {"tree": 5}
    health = next(k for k in d["kpis"] if k["key"] == "health")
    assert health["available"] and health["value"] == 50.0 and "2 healthy of 4" in health["basis"]


def test_open_issues_exclude_resolved_and_group_by_severity(api_for, team):
    worker, mgr = api_for(team.worker), api_for(team.manager)
    a = make_asset(worker)["id"]
    make_issue(worker, a, severity="high")
    make_issue(worker, a, severity="low")
    done = make_issue(worker, a, severity="critical")
    assert (
        mgr.post(
            f"/issues/{done['id']}/transitions", {"to_state": "resolved", "resolution": resolve_body()}
        ).status_code
        == 200
    )

    w = dash(mgr)["work"]
    assert w["open_issues"] == 2
    assert w["open_issues_by_severity"] == {"critical": 0, "high": 1, "medium": 0, "low": 1}


def test_overdue_vs_upcoming_tasks(api_for, team):
    mgr = api_for(team.manager)
    make_task(mgr, title="late", due_at=ago(days=2))
    make_task(mgr, title="soon", due_at=ahead(days=3))
    make_task(mgr, title="far", due_at=ahead(days=30))
    make_task(mgr, title="undated")
    finished = make_task(mgr, title="done late", due_at=ago(days=5))
    for to in ("in_progress", "done"):
        assert mgr.post(f"/tasks/{finished['id']}/transitions", {"to_status": to}).status_code == 200, to

    w = dash(mgr)["work"]
    assert w["open_tasks"] == 4
    assert w["overdue_tasks"] == 1  # a completed task is never overdue
    assert w["tasks_due_next_7_days"] == 1


def test_inspections_due_uses_the_agent_interval(api_for, team):
    api = api_for(team.worker)
    stale = make_asset(api, label="stale")["id"]
    fresh = make_asset(api, label="fresh")["id"]
    observe(api, stale, health_score=80, observed_at=ago(days=40))
    observe(api, fresh, health_score=80)
    w = dash(api)["work"]
    assert w["inspection_interval_days"] == 21
    assert w["inspections_due"] == 1


def test_filters_scope_assets_issues_and_tasks(api_for, team):
    api, mgr = api_for(team.worker), api_for(team.manager)
    z1, z2 = make_location(mgr, "Z1")["id"], make_location(mgr, "Z2")["id"]
    tree = make_asset(api, label="t", location_id=z1)["id"]
    crop = make_asset(api, label="c", kind="crop_batch", location_id=z2)["id"]
    observe(api, tree, health_score=90)
    observe(api, crop, health_score=20)
    make_issue(api, tree, severity="low")
    make_issue(api, crop, severity="high")
    make_task(mgr, asset_id=crop, due_at=ago(days=1))

    assert dash(api)["assets"]["total"] == 2
    in_z1 = dash(api, location_id=z1)
    assert in_z1["assets"]["total"] == 1 and in_z1["assets"]["health"]["healthy"] == 1
    assert in_z1["work"]["open_issues"] == 1 and in_z1["work"]["overdue_tasks"] == 0
    crops = dash(api, kind="crop_batch")
    assert crops["assets"]["by_kind"] == {"crop_batch": 1} and crops["assets"]["health"]["critical"] == 1
    assert crops["work"]["open_issues_by_severity"]["high"] == 1 and crops["work"]["overdue_tasks"] == 1
    assert all(a["asset_id"] in (crop, None) for a in crops["recent_activity"])
    assert dash(api, kind="crop_batch", location_id=z1)["assets"]["total"] == 0


def test_recent_activity_is_newest_first_and_bounded(api_for, team):
    api = api_for(team.worker)
    a = make_asset(api)["id"]
    for i in range(12):
        observe(api, a, health_score=70 + i)
    make_issue(api, a)
    act = dash(api)["recent_activity"]
    assert len(act) == 10
    assert [x["at"] for x in act] == sorted((x["at"] for x in act), reverse=True)
    assert {x["type"] for x in act} <= {"observation", "issue", "task"}


def test_both_modes_share_one_shape_with_mode_specific_kpis(api_for, team):
    green = dash(api_for(team.owner))
    agri = dash(api_for(team.owner, team.agri_ws))
    assert green["mode"] == "green_management" and agri["mode"] == "agricultural_production"
    assert green.keys() == agri.keys()
    assert [k["key"] for k in green["kpis"]] != [k["key"] for k in agri["kpis"]]
    for k in green["kpis"] + agri["kpis"]:
        # an uncomputable KPI says why and carries no number
        assert k["available"] or (k["value"] is None and k["reason"])


def test_viewer_can_read_and_tenants_are_isolated(api_for, team):
    mgr = api_for(team.manager)
    make_asset(mgr)
    assert dash(api_for(team.viewer))["assets"]["total"] == 1
    assert dash(api_for(team.other_owner, team.other_ws))["assets"]["total"] == 0


def test_statement_count_does_not_grow_with_data(api_for, team, world):
    engine = world.maker.kw["bind"]
    api = api_for(team.worker)
    counts: list[int] = []

    def measure() -> int:
        n = 0

        def bump(*_a):
            nonlocal n
            n += 1

        event.listen(engine, "before_cursor_execute", bump)
        try:
            dash(api)
        finally:
            event.remove(engine, "before_cursor_execute", bump)
        return n

    for i in range(3):
        a = make_asset(api, label=f"a{i}")["id"]
        observe(api, a, health_score=60)
        make_issue(api, a)
    counts.append(measure())
    for i in range(3, 30):
        a = make_asset(api, label=f"a{i}")["id"]
        observe(api, a, health_score=60)
    counts.append(measure())
    assert counts[0] == counts[1], counts
