"""MVP rules. Thresholds are per-workspace parameters (defaults shown)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from .base import AssetSnapshot, Finding


@dataclass(frozen=True)
class InspectionGap:
    """RULE: no observation for more than `max_days` -> recommend an inspection task."""

    max_days: int = 21
    key: str = "inspection_gap"

    def evaluate(self, assets: list[AssetSnapshot], now: datetime) -> list[Finding]:
        out = []
        for a in assets:
            if a.last_observed_at is None:
                gap_text = "has never been observed"
            else:
                gap = now - a.last_observed_at
                if gap <= timedelta(days=self.max_days):
                    continue
                gap_text = f"has not been observed for {gap.days} days (limit {self.max_days})"
            out.append(
                Finding(
                    rule_key=self.key,
                    method="rule",
                    subject_ids=(a.asset_id,),
                    title=f"{a.label} {gap_text}",
                    explanation=f"last_observed_at older than {self.max_days} days",
                    severity="medium",
                    proposed_action={"create": "task", "type": "inspect", "asset_id": a.asset_id},
                )
            )
        return out


@dataclass(frozen=True)
class HealthDecline:
    """STATISTICAL: health fell by >= `min_drop` points between the oldest and newest
    observation inside `window_days` (needs >= 2 points). Not a forecast."""

    window_days: int = 14
    min_drop: float = 15.0
    key: str = "health_decline"

    def evaluate(self, assets: list[AssetSnapshot], now: datetime) -> list[Finding]:
        out = []
        cutoff = now - timedelta(days=self.window_days)
        for a in assets:
            pts = sorted((p for p in a.health_history if p.observed_at >= cutoff), key=lambda p: p.observed_at)
            if len(pts) < 2:
                continue
            drop = pts[0].score - pts[-1].score
            if drop >= self.min_drop:
                out.append(
                    Finding(
                        rule_key=self.key,
                        method="statistical",
                        subject_ids=(a.asset_id,),
                        title=f"{a.label} health fell {drop:.0f} points in {self.window_days} days",
                        explanation=f"{pts[0].score:.0f} -> {pts[-1].score:.0f} across {len(pts)} observations",
                        severity="high" if pts[-1].score < 40 else "medium",
                        proposed_action={"create": "issue", "category": "growth_anomaly", "asset_id": a.asset_id},
                    )
                )
        return out


@dataclass(frozen=True)
class SymptomCluster:
    """RULE: >= `min_assets` assets in one zone report the same symptom -> one cluster issue."""

    min_assets: int = 5
    key: str = "symptom_cluster"

    def evaluate(self, assets: list[AssetSnapshot], now: datetime) -> list[Finding]:
        groups: dict[tuple[str, str], list[AssetSnapshot]] = defaultdict(list)
        for a in assets:
            if a.zone is None:
                continue
            for s in set(a.latest_symptoms):
                groups[(a.zone, s)].append(a)
        out = []
        for (zone, symptom), members in sorted(groups.items()):
            if len(members) >= self.min_assets:
                out.append(
                    Finding(
                        rule_key=self.key,
                        method="rule",
                        subject_ids=tuple(m.asset_id for m in members),
                        title=f"{len(members)} plants in {zone} show '{symptom}'",
                        explanation=f"same symptom on >= {self.min_assets} assets in one zone",
                        severity="high",
                        proposed_action={"create": "issue", "category": "disease", "zone": zone},
                    )
                )
        return out


DEFAULT_RULES = (InspectionGap(), HealthDecline(), SymptomCluster())


def run_agent(assets: list[AssetSnapshot], now: datetime, rules=DEFAULT_RULES) -> list[Finding]:
    """Evaluate all rules; drop duplicate dedupe_keys (first wins)."""
    seen: set[str] = set()
    out: list[Finding] = []
    for rule in rules:
        for f in rule.evaluate(assets, now):
            if f.dedupe_key not in seen:
                seen.add(f.dedupe_key)
                out.append(f)
    return out
