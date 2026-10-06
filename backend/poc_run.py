"""Proof-of-concept run of the rules engine on SYNTHETIC sample data (not real observations)."""

from datetime import datetime, timedelta

from app.modules.intelligence.rules.base import AssetSnapshot, HealthPoint
from app.modules.intelligence.rules.mvp_rules import run_agent

NOW = datetime(2026, 10, 6, 9, 0)


def d(n):
    return NOW - timedelta(days=n)


assets = [
    AssetSnapshot("t482", "Tree #482", "Zone 4", d(23), (HealthPoint(d(23), 78),)),
    AssetSnapshot("t101", "Neem #101", "Zone 2", d(2), (HealthPoint(d(12), 82), HealthPoint(d(2), 58))),
    *[AssetSnapshot(f"p{i}", f"Tomato plant P{i}", "Zone B", d(1), (), ("leaf_spot",)) for i in range(1, 7)],
    AssetSnapshot("t007", "Mango #007", "Zone 1", d(3), (HealthPoint(d(3), 90),)),
]

print("SAMPLE DATA - rules engine run @", NOW.date())
for f in run_agent(assets, NOW):
    print(f"[{f.severity.upper():8}] ({f.method}) {f.title}")
    print(f"           why: {f.explanation}")
    a = f.proposed_action
    print(f"           -> propose: create {a['create']} ({a.get('type') or a.get('category')})")
