from datetime import datetime, timedelta

from app.modules.intelligence.rules.base import AssetSnapshot, HealthPoint
from app.modules.intelligence.rules.mvp_rules import (
    CriticalHealth,
    HealthDecline,
    InspectionGap,
    SymptomCluster,
    run_agent,
)

NOW = datetime(2026, 10, 6, 9, 0)


def asset(i, last_days=None, zone="Zone B", symptoms=(), health=()):
    last = None if last_days is None else NOW - timedelta(days=last_days)
    pts = tuple(HealthPoint(NOW - timedelta(days=d), s) for d, s in health)
    return AssetSnapshot(f"a{i}", f"Tree #{i}", zone, last, pts, tuple(symptoms))


def test_inspection_gap_boundary():
    assert InspectionGap().evaluate([asset(1, 21)], NOW) == []  # exactly 21 d: not over limit
    assert len(InspectionGap().evaluate([asset(1, 22)], NOW)) == 1  # 22 d: flagged
    assert len(InspectionGap().evaluate([asset(1, None)], NOW)) == 1  # never observed


def test_health_decline_needs_two_points_and_threshold():
    one = asset(1, 1, health=[(1, 40)])
    small = asset(2, 1, health=[(10, 80), (1, 70)])
    big = asset(3, 1, health=[(10, 82), (1, 62)])
    got = HealthDecline().evaluate([one, small, big], NOW)
    assert [f.subject_ids for f in got] == [("a3",)]
    assert got[0].method == "statistical"


def test_health_decline_ignores_points_outside_window():
    old = asset(1, 1, health=[(30, 90), (1, 60)])  # the 90 is outside 14 d -> one point in window
    assert HealthDecline().evaluate([old], NOW) == []


def test_symptom_cluster_groups_by_zone_and_symptom():
    xs = [asset(i, 1, "Zone B", ["leaf_spot"]) for i in range(5)] + [asset(9, 1, "Zone C", ["leaf_spot"])]
    got = SymptomCluster().evaluate(xs, NOW)
    assert len(got) == 1 and len(got[0].subject_ids) == 5 and "Zone B" in got[0].title


def test_agent_dedupes_and_is_deterministic():
    xs = [asset(i, 30, "Zone B", ["leaf_spot"]) for i in range(5)]
    a, b = run_agent(xs, NOW), run_agent(xs, NOW)
    assert [f.dedupe_key for f in a] == [f.dedupe_key for f in b]
    assert len({f.dedupe_key for f in a}) == len(a)


def snap(i, *, score=None, open_issues=0, inspecting=False, last_days=None, registered_days=None):
    last = None if last_days is None else NOW - timedelta(days=last_days)
    reg = None if registered_days is None else NOW - timedelta(days=registered_days)
    return AssetSnapshot(
        f"a{i}",
        f"Tree #{i}",
        "Z",
        last,
        latest_health_score=score,
        latest_observation_id=f"o{i}",
        open_issue_count=open_issues,
        has_open_inspection_task=inspecting,
        registered_at=reg,
    )


def test_critical_health_boundaries_and_severity():
    rule = CriticalHealth(below=40)
    assert rule.evaluate([snap(1, score=40)], NOW) == []  # not below
    assert rule.evaluate([snap(2, score=None)], NOW) == []  # unknown is not critical
    [high] = rule.evaluate([snap(3, score=39.9)], NOW)
    assert high.severity == "high" and high.method == "rule"
    [crit] = rule.evaluate([snap(4, score=19.9)], NOW)
    assert crit.severity == "critical"
    assert crit.proposed_action["observation_id"] == "o4"


def test_critical_health_is_silent_when_an_issue_is_already_open():
    assert CriticalHealth().evaluate([snap(1, score=5, open_issues=1)], NOW) == []


def test_inspection_gap_ignores_new_assets_and_assets_with_an_open_inspection_task():
    rule = InspectionGap(max_days=21)
    assert rule.evaluate([snap(1, registered_days=3)], NOW) == []  # registered recently
    assert len(rule.evaluate([snap(2, registered_days=30)], NOW)) == 1  # never inspected since registration
    assert rule.evaluate([snap(3, registered_days=30, inspecting=True)], NOW) == []  # someone is on it
    assert rule.evaluate([snap(4, last_days=22, registered_days=90)], NOW)[0].proposed_action["type"] == "inspect"


def test_health_decline_is_silent_when_an_issue_is_open():
    a = asset(1, 1, health=[(10, 90), (1, 50)])
    open_one = AssetSnapshot(**{**a.__dict__, "open_issue_count": 1})
    assert HealthDecline().evaluate([a], NOW) and HealthDecline().evaluate([open_one], NOW) == []


def test_run_agent_proposes_at_most_one_issue_per_asset():
    a = AssetSnapshot(
        "a1",
        "Tree",
        "Z",
        NOW,
        (HealthPoint(NOW - timedelta(days=5), 90), HealthPoint(NOW, 10)),
        latest_health_score=10,
        latest_observation_id="o1",
    )
    findings = run_agent([a], NOW)
    assert [f.rule_key for f in findings] == ["critical_health"]  # health_decline is dropped: same proposal


def test_health_decline_baseline_resets_when_an_issue_is_resolved():
    base = asset(1, 1, health=[(10, 90), (4, 30), (1, 62)])  # fell, was treated, recovered to 62
    assert HealthDecline().evaluate([base], NOW)  # without a resolution it looks like a 28-point decline
    resolved = AssetSnapshot(**{**base.__dict__, "last_resolved_at": NOW - timedelta(days=0.5)})
    assert HealthDecline().evaluate([resolved], NOW) == []  # the handled episode is not re-flagged
    # a NEW decline after the resolution is still detected
    later = asset(2, 0, health=[(3, 85), (0.5, 55)])
    later = AssetSnapshot(**{**later.__dict__, "last_resolved_at": NOW - timedelta(days=5)})
    assert len(HealthDecline().evaluate([later], NOW)) == 1


def test_findings_carry_the_numbers_behind_their_sentence():
    """ADR-081: a client words suggestions in the reader's language from these fields, not from the English title."""
    [crit] = CriticalHealth(below=40).evaluate([snap(4, score=19.9)], NOW)
    assert crit.evidence == {"label": crit.title.split(" health")[0], "score": 19.9, "threshold": 40}
    [fell] = HealthDecline().evaluate([asset(3, 1, health=[(10, 82), (1, 62)])], NOW)
    assert fell.evidence == {
        "label": "Tree #3",
        "from_score": 82,
        "to_score": 62,
        "drop": 20,
        "window_days": 14,
        "observations": 2,
    }
    [gap] = InspectionGap().evaluate([asset(1, 30)], NOW)
    assert (
        gap.evidence["label"] == "Tree #1" and gap.evidence["days_since"] == 30 and gap.evidence["interval_days"] == 21
    )
