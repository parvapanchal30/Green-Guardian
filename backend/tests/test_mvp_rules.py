from datetime import datetime, timedelta

from app.modules.intelligence.rules.base import AssetSnapshot, HealthPoint
from app.modules.intelligence.rules.mvp_rules import HealthDecline, InspectionGap, SymptomCluster, run_agent

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
