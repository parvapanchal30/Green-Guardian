"""Health and growth over time (Monitor pages) and the dashboard Growth KPI: descriptive figures from recorded
observations only, never estimated values."""

from __future__ import annotations

from tests.helpers import ago, make_asset, make_location, observe


def health(api, **params) -> dict:
    r = api.get("/monitor/health", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def growth(api, **params) -> dict:
    r = api.get("/monitor/growth", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def measure(api, asset_id: str, days_ago: int, **values):
    return api.post(
        "/observations", {"asset_id": asset_id, "kind": "growth", "observed_at": ago(days=days_ago), "data": values}
    )


# ------------------------------------------------------------------ health


def test_current_bands_weekly_figures_declines_and_unobserved(api_for, team):
    m = api_for(team.manager)
    falling = make_asset(m, label="Falling")
    rising = make_asset(m, label="Rising")
    make_asset(m, label="Never looked at")
    dead = make_asset(m, label="Dead")
    observe(m, falling["id"], health_score=80, observed_at=ago(days=20))
    observe(m, falling["id"], health_score=35)
    observe(m, rising["id"], health_score=50, observed_at=ago(days=20))
    observe(m, rising["id"], health_score=90)
    observe(m, dead["id"], health_score=10)
    assert m.post(f"/assets/{dead['id']}/lifecycle", {"stage": "dead", "note": "storm damage"}).status_code == 201

    body = health(m, weeks=4)
    assert body["method"] == "statistical"
    assert body["now"] == {"healthy": 1, "at_risk": 0, "critical": 1, "no_data": 1}  # the dead tree is not counted
    assert len(body["weekly"]) == 4 and body["weekly"] == sorted(body["weekly"], key=lambda w: w["week_start"])
    this_week = body["weekly"][-1]
    assert (this_week["observations"], this_week["assets"], this_week["mean_score"]) == (2, 2, 62.5)
    assert (this_week["healthy"], this_week["critical"]) == (1, 1)
    assert [(d["label"], d["change"]) for d in body["declining"]] == [("Falling", -45.0)]  # rising is not a decline
    assert [u["label"] for u in body["not_observed"]] == ["Never looked at"] and body["not_observed_count"] == 1
    assert body["not_observed"][0]["last_observed_at"] is None


def test_scoped_by_kind_and_place_and_bounded(api_for, team):
    m = api_for(team.manager)
    loc = make_location(m, name="East")
    observe(m, make_asset(m, label="Tree in east", location_id=loc["id"])["id"], health_score=30)
    observe(m, make_asset(m, label="Shrub", kind="shrub")["id"], health_score=90)
    assert health(m, location_id=loc["id"])["now"]["critical"] == 1
    assert health(m, location_id=loc["id"])["now"]["healthy"] == 0
    assert health(m, kind="shrub")["now"] == {"healthy": 1, "at_risk": 0, "critical": 0, "no_data": 0}
    assert m.get("/monitor/health", params={"weeks": 0}).json()["code"] == "bad_weeks"
    other = api_for(team.other_owner, team.other_ws)
    assert health(other)["now"] == {"healthy": 0, "at_risk": 0, "critical": 0, "no_data": 0}  # nothing of ours leaks


def test_a_corrected_score_replaces_the_original(api_for, team):
    m = api_for(team.manager)
    a = make_asset(m)
    wrong = observe(m, a["id"], health_score=10, observed_at=ago(days=10))
    observe(m, a["id"], health_score=85, observed_at=ago(days=10), supersedes_id=wrong["observation"]["id"])
    weeks = health(m, weeks=3)["weekly"]
    assert sum(w["critical"] for w in weeks) == 0 and sum(w["healthy"] for w in weeks) == 1


# ------------------------------------------------------------------ growth


def test_measurements_are_validated(api_for, team):
    m = api_for(team.manager)
    a = make_asset(m)
    for bad in ({"height_cm": "tall"}, {"height_cm": -1}, {"girth_cm": 99_999}, {"canopy_m": True}):
        r = measure(m, a["id"], 1, **bad)
        assert r.status_code == 422 and r.json()["code"] == "bad_measurement", bad
    assert measure(m, a["id"], 1, height_cm=120, girth_cm=30.5, canopy_m=2.4).status_code == 201


def test_growth_compares_measurements_far_enough_apart(api_for, team):
    m = api_for(team.manager)
    grew = make_asset(m, label="Grew")
    too_soon = make_asset(m, label="Too soon")
    once = make_asset(m, label="Once")
    measure(m, grew["id"], 60, height_cm=100, girth_cm=20)
    measure(m, grew["id"], 0, height_cm=130)
    measure(m, too_soon["id"], 10, height_cm=50)
    measure(m, too_soon["id"], 0, height_cm=60)
    measure(m, once["id"], 5, height_cm=40)

    body = growth(m)
    rows = {r["label"]: r for r in body["assets"]}
    g = rows["Grew"]
    assert (g["first"], g["latest"], g["change"], g["change_pct"], g["measurements"]) == (100, 130, 30, 30.0, 2)
    assert 180 <= g["per_year"] <= 185  # 30 cm in 60 days
    assert rows["Too soon"]["change"] is None and rows["Once"]["change"] is None  # nothing to compare yet
    assert (body["measured_assets"], body["comparable_assets"], body["median_change_pct"]) == (3, 1, 30.0)
    assert [r["label"] for r in growth(m, metric="girth_cm")["assets"]] == ["Grew"]
    assert m.get("/monitor/growth", params={"metric": "weight"}).status_code == 422

    series = m.get(f"/assets/{grew['id']}/growth").json()["measurements"]
    assert [(s["height_cm"], s["girth_cm"]) for s in series] == [(100, 20), (130, None)]


def test_the_dashboard_growth_kpi(api_for, team):
    m = api_for(team.manager)

    def kpi():
        return next(k for k in m.get("/dashboard").json()["kpis"] if k["key"] == "growth")

    assert kpi()["available"] is False and "30 days apart" in kpi()["reason"]
    a, b = make_asset(m, label="A"), make_asset(m, label="B")
    for asset, start, end in ((a, 100, 110), (b, 200, 260)):
        measure(m, asset["id"], 45, height_cm=start)
        measure(m, asset["id"], 0, height_cm=end)
    k = kpi()
    assert (k["available"], k["value"], k["unit"]) == (True, 20.0, "%")  # median of 10% and 30%
    assert "2 assets" in k["basis"]
