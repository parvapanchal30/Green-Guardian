"""Irrigation deferral end to end: weather port -> rule -> recommendation -> a person's decision -> task and outcome.

A fake `WeatherContextProvider` replaces the weather stack, so no test reaches a real forecast service.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.modules.intelligence.ports import WeatherContext, get_weather_context_provider
from app.modules.workspaces.models import Workspace
from tests.helpers import ahead, make_asset, make_task, observe


class FakeWeather:
    def __init__(self, ctx: WeatherContext | None):
        self.ctx = ctx
        self.calls: list[tuple[float, float]] = []

    def context_for(self, latitude, longitude, now):
        self.calls.append((latitude, longitude))
        return self.ctx


def rainy(**over) -> WeatherContext:
    base = dict(
        latitude=19.2,
        longitude=72.9,
        as_of=datetime.now(UTC),
        source="fake-forecast",
        rain_next_24h_mm=14.0,
        max_rain_probability_pct=90.0,
        temperature_c=26.0,
        soil_moisture_top=0.3,
    )
    base.update(over)
    return WeatherContext(**base)  # type: ignore[arg-type]


def aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes, PostgreSQL aware ones; both mean UTC here."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def use_weather(app, fake: FakeWeather) -> FakeWeather:
    app.dependency_overrides[get_weather_context_provider] = lambda: fake
    return fake


def setup_watering(api, *, due_in_hours: float = 6, **asset):
    """A located, recently observed asset with one watering task due soon."""
    a = make_asset(api, label="Mango #7", latitude=19.2, longitude=72.9, **asset)
    observe(api, a["id"], health_score=85)
    task = make_task(api, title="Water Mango #7", type="water", asset_id=a["id"], due_at=ahead(hours=due_in_hours))
    return a, task


def irrigation_recs(api, status="open"):
    return [
        r
        for r in api.get("/recommendations", params={"status": status}).json()["items"]
        if r["rule_key"] == "irrigation_defer"
    ]


def test_forecast_rain_before_a_watering_task_produces_an_explained_advisory(api_for, team, app):
    manager = api_for(team.manager)
    asset, task = setup_watering(manager)
    fake = use_weather(app, FakeWeather(rainy()))
    out = manager.post("/agent/run").json()
    recs = [r for r in out["created"] if r["rule_key"] == "irrigation_defer"]
    assert len(recs) == 1 and fake.calls == [(19.2, 72.9)]
    rec = recs[0]
    assert rec["method"] == "rule" and rec["severity"] == "low" and rec["asset_id"] == asset["id"]
    assert rec["proposed_action"]["create"] == "defer_task" and rec["proposed_action"]["task_id"] == task["id"]
    assert "ADVISORY" in rec["explanation"] and "14 mm" in rec["explanation"]
    assert rec["evidence"]["rule"] == {"key": "irrigation_defer", "version": 1} and rec["evidence"]["evaluated_at"]
    ev = rec["evidence"]["inputs"]
    assert ev["kind"] == "advisory_forecast_based" and ev["forecast"]["source"] == "fake-forecast"
    assert ev["task"]["key"] == task["key"] and any("soil moisture" in n for n in ev["not_known"])
    assert rec["agent_run_id"] == out["run"]["id"] and rec["rule_version"] == 1
    assert (
        out["run"]["diagnostics"]["weather"]["requested"] is True
        and out["run"]["diagnostics"]["weather"]["locations"] == 1
    )


def test_accepting_defers_the_task_records_history_and_the_outcome(api_for, team, app):
    manager = api_for(team.manager)
    asset, task = setup_watering(manager, due_in_hours=6)
    use_weather(app, FakeWeather(rainy()))
    rec = [r for r in manager.post("/agent/run").json()["created"] if r["rule_key"] == "irrigation_defer"][0]
    old_due = datetime.fromisoformat(manager.get(f"/tasks/{task['id']}").json()["due_at"])

    accepted = manager.post(f"/recommendations/{rec['id']}/accept", {})
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert (
        body["status"] == "accepted"
        and body["accepted_entity_type"] == "task"
        and body["accepted_entity_id"] == task["id"]
    )
    assert (
        body["outcome"] == "deferral_applied"
        and body["outcome_at"] is not None
        and task["key"] in body["outcome_detail"]
    )

    detail = manager.get(f"/tasks/{task['id']}").json()
    new_due = datetime.fromisoformat(detail["due_at"])
    assert timedelta(hours=23, minutes=59) <= new_due - old_due <= timedelta(hours=24, minutes=1)
    assert detail["status"] == "todo" and any(
        "Deferred on advice irrigation_defer" in (h.get("note") or "") for h in detail["history"]
    )
    # the suggestion is spent: re-running does not propose the same deferral again for the moved task
    again = manager.post("/agent/run").json()
    assert [r for r in again["created"] if r["rule_key"] == "irrigation_defer"] == []


def test_a_person_can_choose_the_new_due_date(api_for, team, app):
    manager = api_for(team.manager)
    _, task = setup_watering(manager)
    use_weather(app, FakeWeather(rainy()))
    rec = [r for r in manager.post("/agent/run").json()["created"] if r["rule_key"] == "irrigation_defer"][0]
    chosen = datetime.now(UTC) + timedelta(days=3)
    manager.post(f"/recommendations/{rec['id']}/accept", {"due_at": chosen.isoformat()})
    due = datetime.fromisoformat(manager.get(f"/tasks/{task['id']}").json()["due_at"])
    assert abs((aware(due) - chosen).total_seconds()) < 2


def test_a_task_that_already_started_cannot_be_deferred(api_for, team, app):
    manager = api_for(team.manager)
    _, task = setup_watering(manager)
    use_weather(app, FakeWeather(rainy()))
    rec = [r for r in manager.post("/agent/run").json()["created"] if r["rule_key"] == "irrigation_defer"][0]
    assert manager.post(f"/tasks/{task['id']}/transitions", {"to_status": "in_progress"}).status_code == 200
    r = manager.post(f"/recommendations/{rec['id']}/accept", {})
    assert r.status_code == 409 and r.json()["code"] == "task_not_deferrable"
    assert irrigation_recs(manager)  # still open; nothing half-done


def test_viewers_and_workers_cannot_act_on_advice(api_for, team, app):
    manager = api_for(team.manager)
    setup_watering(manager)
    use_weather(app, FakeWeather(rainy()))
    rec = [r for r in manager.post("/agent/run").json()["created"] if r["rule_key"] == "irrigation_defer"][0]
    for member in (team.viewer, team.worker):
        assert api_for(member).post(f"/recommendations/{rec['id']}/accept", {}).status_code == 403


def test_no_watering_task_means_no_weather_request_at_all(api_for, team, app):
    manager = api_for(team.manager)
    a = make_asset(manager, label="Dry run", latitude=19.2, longitude=72.9)
    observe(manager, a["id"], health_score=85)
    fake = use_weather(app, FakeWeather(rainy()))
    out = manager.post("/agent/run").json()
    assert fake.calls == [] and out["run"]["diagnostics"]["weather"]["requested"] is False
    assert [r for r in out["created"] if r["rule_key"] == "irrigation_defer"] == []


def test_unavailable_weather_is_reported_and_nothing_is_suggested(api_for, team, app):
    manager = api_for(team.manager)
    setup_watering(manager)
    fake = use_weather(app, FakeWeather(None))
    out = manager.post("/agent/run").json()
    assert len(fake.calls) == 1 and irrigation_recs(manager) == []
    diag = out["run"]["diagnostics"]
    assert diag["weather"]["unavailable"] == 1 and diag["skipped"].get("weather_unavailable") == 1


def test_an_asset_without_a_position_is_skipped_with_a_reason(api_for, team, app):
    manager = api_for(team.manager)
    a = make_asset(manager, label="Unplaced")
    observe(manager, a["id"], health_score=85)
    make_task(manager, title="Water it", type="water", asset_id=a["id"], due_at=ahead(hours=4))
    fake = use_weather(app, FakeWeather(rainy()))
    out = manager.post("/agent/run").json()
    assert fake.calls == [] and out["run"]["diagnostics"]["skipped"].get("no_location") == 1


def test_signs_of_water_stress_withhold_the_suggestion(api_for, team, app):
    manager = api_for(team.manager)
    a, _ = setup_watering(manager)
    observe(manager, a["id"], health_score=70, symptoms=["wilting"])
    use_weather(app, FakeWeather(rainy()))
    out = manager.post("/agent/run").json()
    assert irrigation_recs(manager) == [] and out["run"]["diagnostics"]["skipped"].get("water_stress_signs") == 1


def test_modelled_soil_moisture_alone_never_triggers_a_suggestion(api_for, team, app):
    manager = api_for(team.manager)
    setup_watering(manager)
    use_weather(app, FakeWeather(rainy(rain_next_24h_mm=0.0, max_rain_probability_pct=5.0, soil_moisture_top=0.5)))
    out = manager.post("/agent/run").json()
    assert irrigation_recs(manager) == [] and out["run"]["diagnostics"]["skipped"].get("below_threshold") == 1


def test_when_the_forecast_clears_the_stale_suggestion_expires_but_stays_in_history(api_for, team, app):
    manager = api_for(team.manager)
    setup_watering(manager)
    fake = use_weather(app, FakeWeather(rainy()))
    first = manager.post("/agent/run").json()
    assert len(irrigation_recs(manager)) == 1
    fake.ctx = rainy(rain_next_24h_mm=0.2, max_rain_probability_pct=5)
    second = manager.post("/agent/run").json()
    assert second["expired"] == 1 and second["run"]["recommendations_expired"] == 1
    assert irrigation_recs(manager) == []
    expired = irrigation_recs(manager, "expired")
    assert len(expired) == 1 and expired[0]["agent_run_id"] == first["run"]["id"]


def test_saving_an_observation_does_not_expire_irrigation_advice_it_could_not_re_check(api_for, team, app):
    manager = api_for(team.manager)
    a, _ = setup_watering(manager)
    use_weather(app, FakeWeather(rainy()))
    manager.post("/agent/run")
    assert len(irrigation_recs(manager)) == 1
    observe(manager, a["id"], health_score=84)  # evaluated inline without a forecast: the rule cannot see the rain
    assert len(irrigation_recs(manager)) == 1  # so the advice is kept, not wrongly expired


def test_completing_the_watering_task_expires_the_advice_for_it(api_for, team, app):
    manager = api_for(team.manager)
    _, task = setup_watering(manager)
    use_weather(app, FakeWeather(rainy()))
    manager.post("/agent/run")
    manager.post(f"/tasks/{task['id']}/transitions", {"to_status": "in_progress"})
    manager.post(f"/tasks/{task['id']}/transitions", {"to_status": "done"})
    assert manager.post("/agent/run").json()["expired"] == 1 and irrigation_recs(manager) == []


def test_a_dismissed_suggestion_is_not_repeated(api_for, team, app):
    manager = api_for(team.manager)
    setup_watering(manager)
    use_weather(app, FakeWeather(rainy()))
    rec = [r for r in manager.post("/agent/run").json()["created"] if r["rule_key"] == "irrigation_defer"]
    assert (
        manager.post(f"/recommendations/{rec[0]['id']}/dismiss", {"reason": "Hand-watering anyway"}).status_code == 200
    )
    again = manager.post("/agent/run").json()
    assert [r for r in again["created"] if r["rule_key"] == "irrigation_defer"] == []
    assert again["run"]["diagnostics"]["dismissed_recently"] >= 1


def test_the_default_wiring_works_with_the_mock_provider_and_makes_no_network_call(api_for, team):
    manager = api_for(team.manager)
    setup_watering(manager)
    r = manager.post("/agent/run")  # no override: composition root -> ForecastWeatherContext -> MockWeatherProvider
    assert r.status_code == 200 and r.json()["run"]["diagnostics"]["weather"]["requested"] is True


def test_the_irrigation_rule_can_be_switched_off_per_workspace(api_for, team, app, world):
    manager = api_for(team.manager)
    setup_watering(manager)
    fake = use_weather(app, FakeWeather(rainy()))
    with world.db() as db:
        db.execute(
            update(Workspace)
            .where(Workspace.id == uuid.UUID(team.ws))
            .values(settings={"agent": {"irrigation_defer_enabled": False}})
        )
        db.commit()
    out = manager.post("/agent/run").json()
    assert "irrigation_defer" not in {r["key"] for r in out["rules"]} and irrigation_recs(manager) == []
    assert fake.calls == []  # no suggestion, and no provider request either
