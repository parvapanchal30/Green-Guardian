"""MVP rules. Thresholds are per-workspace parameters (defaults shown)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from .base import AssetSnapshot, Finding, Skip


@dataclass(frozen=True)
class InspectionGap:
    """RULE (v2): nobody has looked at the asset for more than `max_days` -> recommend an inspection task.

    "Looked at" means the most recent of: an observation, a completed inspection task, or activity on one of the asset's
    issues (a status change). So work that was done but left no observation, or an issue that is being worked, is not
    nagged about, while a forgotten open issue does not suppress the reminder forever. Assets registered within the
    interval and assets with an open inspection task are skipped. The evidence records every date used.
    """

    max_days: int = 21
    key: str = "inspection_gap"

    def evaluate(self, assets: list[AssetSnapshot], now: datetime) -> list[Finding]:
        out = []
        for a in assets:
            if a.has_open_inspection_task:
                continue  # somebody is already on it; do not nag
            signals = {
                "observation": a.last_observed_at,
                "completed inspection task": a.last_inspection_completed_at,
                "issue activity": a.last_issue_activity_at,
            }
            present = {k: v for k, v in signals.items() if v is not None}
            if present:
                basis, last = max(present.items(), key=lambda kv: kv[1])
                gap = now - last
                if gap <= timedelta(days=self.max_days):
                    continue
                days = gap.days
                headline = f"has not been looked at for {days} days (limit {self.max_days})"
                detail = f"last attention: {basis} on {last.date().isoformat()}, {days} days ago"
            else:
                if a.registered_at is not None and (now - a.registered_at) <= timedelta(days=self.max_days):
                    continue  # registered recently: nothing is overdue yet
                last, days, basis = None, None, "registration"
                headline = "has never been observed"
                detail = "no observation, completed inspection or issue activity is recorded"
            overdue_days = None if days is None else days - self.max_days
            out.append(
                Finding(
                    rule_key=self.key,
                    method="rule",
                    subject_ids=(a.asset_id,),
                    title=f"{a.label} {headline}",
                    explanation=f"{detail}; the inspection interval is {self.max_days} days and no inspection task "
                    "is open",
                    severity="high" if days is not None and days > 2 * self.max_days else "medium",
                    proposed_action={"create": "task", "type": "inspect", "asset_id": a.asset_id},
                    evidence={
                        "interval_days": self.max_days,
                        "basis": basis,
                        "last_attention_at": last.isoformat() if last else None,
                        "days_since": days,
                        "days_overdue": overdue_days,
                        "signals": {k: v.isoformat() for k, v in present.items()},
                        "open_inspection_task": False,
                        "open_issues": a.open_issue_count,
                    },
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
            if a.open_issue_count > 0:
                continue  # an issue already tracks this asset
            # Only scores recorded after the last resolved issue count: a decline that was handled is not news.
            pts = sorted(
                (
                    p
                    for p in a.health_history
                    if p.observed_at >= cutoff and not (a.last_resolved_at and p.observed_at <= a.last_resolved_at)
                ),
                key=lambda p: p.observed_at,
            )
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


@dataclass(frozen=True)
class CriticalHealth:
    """RULE: the latest recorded health score is below the critical threshold and no issue is open for the asset ->
    recommend opening a Botanical Issue. A threshold check on recorded data, not a prediction."""

    below: float = 40.0
    key: str = "critical_health"

    def evaluate(self, assets: list[AssetSnapshot], now: datetime) -> list[Finding]:
        out = []
        for a in assets:
            score = a.latest_health_score
            if score is None or score >= self.below or a.open_issue_count > 0:
                continue
            out.append(
                Finding(
                    rule_key=self.key,
                    method="rule",
                    subject_ids=(a.asset_id,),
                    title=f"{a.label} health is critical ({score:.0f})",
                    explanation=f"latest health score {score:.0f} is below the critical threshold {self.below:g} "
                    "and the asset has no open issue",
                    severity="critical" if score < self.below / 2 else "high",
                    proposed_action={
                        "create": "issue",
                        "category": "growth_anomaly",
                        "asset_id": a.asset_id,
                        "observation_id": a.latest_observation_id,
                    },
                )
            )
        return out


# Order matters: the first rule that proposes an issue for an asset wins (see run_agent).
DEFAULT_RULES = (CriticalHealth(), HealthDecline(), InspectionGap(), SymptomCluster())


def run_agent_detailed(
    assets: list[AssetSnapshot], now: datetime, rules=DEFAULT_RULES
) -> tuple[list[Finding], list[Skip]]:
    """Evaluate all rules. Returns the findings (duplicate dedupe_keys dropped, first wins; at most one "create issue"
    proposal per asset) and what rules deliberately skipped (for the run record)."""
    seen: set[str] = set()
    issue_proposed_for: set[str] = set()
    out: list[Finding] = []
    skips: list[Skip] = []
    for rule in rules:
        detailed = getattr(rule, "evaluate_detailed", None)
        if detailed is not None:
            found, skipped = detailed(assets, now)
            skips.extend(skipped)
        else:
            found = rule.evaluate(assets, now)
        for f in found:
            if f.dedupe_key in seen:
                continue
            if f.proposed_action.get("create") == "issue" and len(f.subject_ids) == 1:
                if f.subject_ids[0] in issue_proposed_for:
                    continue
                issue_proposed_for.add(f.subject_ids[0])
            seen.add(f.dedupe_key)
            out.append(f)
    return out, skips


def run_agent(assets: list[AssetSnapshot], now: datetime, rules=DEFAULT_RULES) -> list[Finding]:
    """Findings only (see `run_agent_detailed`)."""
    return run_agent_detailed(assets, now, rules)[0]
