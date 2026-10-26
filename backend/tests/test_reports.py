"""Analytics and Impact reports: counts and shares of recorded events in a period, per workspace, never estimates."""

from __future__ import annotations

from tests.helpers import ago, make_asset, make_issue, make_task, observe, resolve_body, species_id


def report(api, kind: str, **params) -> dict:
    r = api.get(f"/reports/{kind}", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_analytics_counts_what_happened_in_the_period(api_for, team):
    m, w = api_for(team.manager), api_for(team.worker)
    tree = make_asset(m)
    observe(w, tree["id"], health_score=30)
    observe(w, tree["id"], notes="checked", data={"height_cm": 200})
    issue = make_issue(m, tree["id"], severity="high")
    on_time = make_task(
        m, title="Spray", type="treat", asset_id=tree["id"], due_at=ago(days=-2), assignee_id=str(team.worker.id)
    )
    late = make_task(
        m, title="Water", type="water", asset_id=tree["id"], due_at=ago(days=2), assignee_id=str(team.worker.id)
    )
    make_task(m, title="Overdue", asset_id=tree["id"], due_at=ago(days=1))
    for t in (on_time, late):
        assert (
            w.post(
                f"/tasks/{t['id']}/transitions",
                {"to_status": "done", "action": {"kind": t["type"], "product": "Neem oil"}},
            ).status_code
            == 200
        )
    resolved = m.post(f"/issues/{issue['id']}/transitions", {"to_state": "resolved", "resolution": resolve_body()})
    assert resolved.status_code == 200, resolved.text

    r = report(m, "analytics")
    assert r["method"] == "statistical"
    assert (r["issues"]["opened"], r["issues"]["closed"], r["issues"]["still_open"]) == (1, 1, 0)
    assert r["issues"]["opened_by_severity"] == {"high": 1} and r["issues"]["closed_by_outcome"] == {"fixed": 1}
    assert r["issues"]["median_days_to_close"] is not None
    t = r["tasks"]
    assert (t["created"], t["completed"], t["completed_with_due_date"], t["completed_on_time"], t["on_time_pct"]) == (
        3,
        2,
        2,
        1,
        50.0,
    )
    assert t["overdue_now"] == 1 and t["completed_by_type"] == {"treat": 1, "water": 1}
    assert r["actions"]["recorded"] == 2 and r["actions"]["top_products"] == [{"name": "Neem oil", "count": 2}]
    o = r["observations"]
    assert (o["recorded"], o["with_health_score"], o["with_measurements"], o["assets_observed"]) == (
        3,
        2,
        1,
        1,
    )  # the helper scores 80 by default; the follow-up check has no score
    assert r["agent"]["suggested"] >= 1  # the critical score produced a suggestion


def test_the_period_excludes_older_events_and_is_validated(api_for, team):
    m = api_for(team.manager)
    tree = make_asset(m)
    observe(m, tree["id"], health_score=80, observed_at=ago(days=200))
    assert report(m, "analytics", since=ago(days=30))["observations"]["recorded"] == 0
    assert report(m, "analytics", since=ago(days=365))["observations"]["recorded"] == 1
    assert (
        m.get("/reports/analytics", params={"since": ago(days=1), "until": ago(days=2)}).json()["code"] == "bad_period"
    )
    assert m.get("/reports/impact", params={"since": ago(days=2000)}).json()["code"] == "period_too_long"


def test_reports_are_per_workspace(api_for, team):
    m = api_for(team.manager)
    observe(m, make_asset(m)["id"], health_score=50)
    other = report(api_for(team.other_owner, team.other_ws), "analytics")
    assert other["observations"]["recorded"] == 0 and other["issues"]["opened"] == 0


def test_impact_planting_survival_health_growth_canopy(api_for, team):
    m = api_for(team.manager)
    neem, mango = species_id(m, "Neem"), species_id(m, "Mango")
    a = make_asset(m, label="A", species_id=neem, planted_at=ago(days=20)[:10])
    b = make_asset(m, label="B", species_id=neem)
    c = make_asset(m, label="C", species_id=mango)
    assert m.post(f"/assets/{c['id']}/lifecycle", {"stage": "dead", "note": "storm damage"}).status_code == 201
    observe(m, a["id"], health_score=50, observed_at=ago(days=200))  # before a 90-day period: at risk
    observe(m, a["id"], health_score=85, observed_at=ago(days=10))  # at its end: healthy
    observe(m, b["id"], health_score=90, observed_at=ago(days=200))
    observe(m, b["id"], notes="measured", data={"height_cm": 100, "canopy_m": 4}, observed_at=ago(days=80))
    observe(m, b["id"], notes="measured", data={"height_cm": 120, "canopy_m": 2}, observed_at=ago(days=5))

    r = report(m, "impact", since=ago(days=90))
    p = r["planting"]
    assert (p["registered"], p["planted"]) == (3, 1)
    assert p["by_species"][0] == {"name": "Neem", "count": 2}
    s = r["survival"]
    assert (s["alive"], s["dead"], s["rate"]) == (2, 1, 66.7)
    assert {x["species"]: (x["alive"], x["dead"]) for x in s["by_species"]} == {"Neem": (2, 0), "Mango": (0, 1)}
    h = r["health"]
    assert (h["assets_compared"], h["healthy_share_start"], h["healthy_share_end"]) == (2, 50.0, 100.0)
    assert r["growth"] == {"comparable_assets": 1, "median_height_change_pct": 20.0}
    assert (r["canopy"]["trees_measured"], r["canopy"]["area_m2"]) == (1, 3.1)  # pi * (2 / 2)^2, the LATEST width
    assert r["coverage"]["available"] is False and "zone areas" in r["coverage"]["reason"]


def test_impact_with_nothing_recorded_says_so(api_for, team):
    r = report(api_for(team.manager), "impact")
    assert r["survival"]["rate"] is None and r["health"]["healthy_share_start"] is None
    assert r["canopy"]["area_m2"] is None and r["growth"]["median_height_change_pct"] is None
