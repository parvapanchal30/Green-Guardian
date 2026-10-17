"""Irrigation deferral rule: pure function tests. No database, no weather provider, no network.

The rule is advisory and forecast-based. These tests pin down what it must NOT do as much as what it does:
soil moisture never triggers it, water-stress signs withhold it, and missing inputs are reported rather than guessed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.modules.intelligence.ports import WeatherContext
from app.modules.intelligence.rules.base import AssetSnapshot, WaterTask
from app.modules.intelligence.rules.irrigation import NOT_KNOWN, IrrigationDeferral

NOW = datetime(2026, 10, 18, 6, 0, tzinfo=UTC)


def weather(**over) -> WeatherContext:
    base = dict(
        latitude=19.2,
        longitude=72.9,
        as_of=NOW,
        source="mock",
        rain_next_24h_mm=12.0,
        max_rain_probability_pct=90.0,
        temperature_c=27.0,
        soil_moisture_top=0.31,
    )
    base.update(over)
    return WeatherContext(**base)  # type: ignore[arg-type]


def snap(*, tasks=None, w="default", **over) -> AssetSnapshot:
    tasks = tasks if tasks is not None else (WaterTask("t1", "T-001", "todo", NOW + timedelta(hours=6)),)
    base = dict(
        asset_id="a1",
        label="Neem #1",
        zone=None,
        last_observed_at=NOW - timedelta(days=1),
        latitude=19.2,
        longitude=72.9,
        position_source="asset",
        open_water_tasks=tuple(tasks),
        weather=weather() if w == "default" else w,
        weather_status="ok",
    )
    base.update(over)
    return AssetSnapshot(**base)  # type: ignore[arg-type]


rule = IrrigationDeferral()


def reasons(skips) -> list[str]:
    return [s.reason for s in skips]


def test_heavy_likely_rain_before_a_watering_task_is_due_yields_an_advisory_finding():
    findings, skips = rule.evaluate_detailed([snap()], NOW)
    assert skips == [] and len(findings) == 1
    f = findings[0]
    assert f.rule_key == "irrigation_defer" and f.method == "rule" and f.severity == "low"
    assert f.proposed_action["create"] == "defer_task" and f.proposed_action["task_id"] == "t1"
    assert f.dedupe_key == "irrigation_defer:a1:t1"
    assert "ADVISORY" in f.explanation and "not on a measurement of soil moisture" in f.explanation
    assert f.evidence["kind"] == "advisory_forecast_based"
    assert f.evidence["forecast"]["rain_next_24h_mm"] == 12.0
    assert f.evidence["thresholds"] == {"min_rain_mm": 5.0, "min_probability_pct": 70.0, "lookahead_hours": 24}


def test_the_finding_lists_what_the_system_does_not_know():
    f = rule.evaluate([snap()], NOW)[0]
    assert tuple(f.evidence["not_known"]) == NOT_KNOWN
    text = " ".join(f.evidence["not_known"])
    for missing in ("soil moisture", "observed rainfall", "water requirements", "irrigation"):
        assert missing in text


def test_modelled_soil_moisture_is_context_only_and_never_a_trigger():
    # very wet modelled soil but little forecast rain: no finding
    wet_but_dry_forecast = snap(w=weather(rain_next_24h_mm=0.4, max_rain_probability_pct=10, soil_moisture_top=0.45))
    findings, skips = rule.evaluate_detailed([wet_but_dry_forecast], NOW)
    assert findings == [] and reasons(skips) == ["below_threshold"]
    # very dry modelled soil with heavy rain: still a finding, and the value is labelled as a model estimate
    dry = rule.evaluate([snap(w=weather(soil_moisture_top=0.02))], NOW)[0]
    assert "model estimate" in dry.explanation
    assert "not measured" in dry.evidence["forecast"]["soil_moisture_note"]
    # no soil moisture at all: finding still produced, nothing invented
    none = rule.evaluate([snap(w=weather(soil_moisture_top=None))], NOW)[0]
    assert none.evidence["forecast"]["soil_moisture_top_modelled"] is None and "m3/m3" not in none.explanation


def test_rain_amount_and_probability_must_both_reach_their_thresholds():
    assert rule.evaluate([snap(w=weather(rain_next_24h_mm=4.9))], NOW) == []
    assert rule.evaluate([snap(w=weather(max_rain_probability_pct=69.0))], NOW) == []
    assert len(rule.evaluate([snap(w=weather(rain_next_24h_mm=5.0, max_rain_probability_pct=70.0))], NOW)) == 1


def test_water_stress_signs_withhold_the_suggestion():
    findings, skips = rule.evaluate_detailed([snap(water_stress_signs=("wilting",))], NOW)
    assert findings == [] and reasons(skips) == ["water_stress_signs"]


def test_missing_inputs_are_reported_not_guessed():
    cases = {
        "weather_unavailable": snap(w=None, weather_status="unavailable"),
        "no_location": snap(latitude=None, longitude=None, w=None, weather_status="no_location"),
        "forecast_incomplete": snap(w=weather(rain_next_24h_mm=None)),
        "forecast_incomplete ": snap(w=weather(max_rain_probability_pct=None)),
    }
    for expected, s in cases.items():
        findings, skips = rule.evaluate_detailed([s], NOW)
        assert findings == [] and reasons(skips) == [expected.strip()], expected


def test_only_tasks_that_have_not_started_and_fall_in_the_forecast_window_are_considered():
    started = WaterTask("t2", "T-002", "in_progress", NOW + timedelta(hours=2))
    blocked = WaterTask("t3", "T-003", "blocked", NOW + timedelta(hours=2))
    no_due = WaterTask("t4", "T-004", "todo", None)
    far = WaterTask("t5", "T-005", "todo", NOW + timedelta(days=5))
    long_overdue = WaterTask("t6", "T-006", "todo", NOW - timedelta(days=3))
    findings, skips = rule.evaluate_detailed([snap(tasks=[started, blocked, no_due, far, long_overdue])], NOW)
    assert findings == []
    assert sorted(reasons(skips)) == ["no_due_date", "task_started_or_blocked", "task_started_or_blocked"]


def test_a_task_slightly_overdue_is_still_a_candidate_and_each_task_gets_its_own_suggestion():
    overdue = WaterTask("t7", "T-007", "todo", NOW - timedelta(hours=3))
    soon = WaterTask("t8", "T-008", "todo", NOW + timedelta(hours=10))
    findings = rule.evaluate([snap(tasks=[overdue, soon])], NOW)
    assert sorted(f.dedupe_key for f in findings) == ["irrigation_defer:a1:t7", "irrigation_defer:a1:t8"]
    assert "3 h ago" in next(f for f in findings if f.proposed_action["task_id"] == "t7").explanation


def test_assets_without_an_open_watering_task_are_ignored_silently():
    findings, skips = rule.evaluate_detailed([snap(tasks=[])], NOW)
    assert findings == [] and skips == []


def test_thresholds_are_configurable_and_the_lookahead_is_capped_at_the_forecast_window():
    strict = IrrigationDeferral(min_rain_mm=20.0)
    assert strict.evaluate([snap()], NOW) == []
    later = WaterTask("t9", "T-009", "todo", NOW + timedelta(hours=30))
    # a 48 h lookahead cannot extend beyond the 24 h the weather summary covers
    assert IrrigationDeferral(lookahead_hours=48).evaluate([snap(tasks=[later])], NOW) == []
