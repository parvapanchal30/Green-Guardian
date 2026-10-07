"""Runs the Botanical Operations Agent (rules) for a workspace and persists its recommendations.

Deterministic and explainable: it reads recorded data, applies thresholds, and writes `Recommendation` rows that a
person accepts or dismisses. It never creates issues or tasks by itself, and it produces no ML or LLM output.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.timeutil import as_utc, utcnow
from app.modules.assets.models import AssetState, BiologicalAsset
from app.modules.locations.models import Location
from app.modules.observations.models import Observation
from app.modules.tasks.models import OPEN_TASK_STATUSES, Task, TaskType

from .models import Recommendation, RecommendationStatus
from .rules.base import AssetSnapshot, Finding, HealthPoint, Rule
from .rules.mvp_rules import CriticalHealth, HealthDecline, InspectionGap, run_agent

HISTORY_WINDOW_DAYS = 30


@dataclass(frozen=True)
class AgentSettings:
    """Per-workspace thresholds, stored under `workspace.settings["agent"]`; defaults apply for anything missing."""

    inspection_gap_days: int = 21
    critical_health_below: float = 40.0
    decline_window_days: int = 14
    decline_min_drop: float = 15.0
    dismiss_suppress_days: int = 7

    @classmethod
    def from_workspace(cls, settings: dict | None) -> AgentSettings:
        raw = (settings or {}).get("agent", {}) or {}
        out: dict[str, Any] = {}
        for name, caster in (
            ("inspection_gap_days", int),
            ("critical_health_below", float),
            ("decline_window_days", int),
            ("decline_min_drop", float),
            ("dismiss_suppress_days", int),
        ):
            if name in raw:
                try:
                    value = caster(raw[name])
                except (TypeError, ValueError):
                    continue  # a malformed override falls back to the default rather than breaking the agent
                if value > 0:
                    out[name] = value
        return cls(**out)

    def rules(self) -> tuple[Rule, ...]:
        # Order matters: the first rule proposing an issue for an asset wins. SymptomCluster needs multi-asset issues
        # and is not wired into the workspace runner yet.
        return (
            CriticalHealth(below=self.critical_health_below),
            HealthDecline(window_days=self.decline_window_days, min_drop=self.decline_min_drop),
            InspectionGap(max_days=self.inspection_gap_days),
        )


def describe_rules(cfg: AgentSettings) -> list[dict]:
    return [
        {
            "key": "critical_health",
            "method": "rule",
            "description": "Latest health score below the critical threshold and no open issue → recommend an issue.",
            "parameters": {"critical_health_below": cfg.critical_health_below},
        },
        {
            "key": "health_decline",
            "method": "statistical",
            "description": "Health fell by at least the minimum drop within the window (two or more scores) and no "
            "open issue → recommend an issue. A comparison of recorded values, not a forecast.",
            "parameters": {"decline_window_days": cfg.decline_window_days, "decline_min_drop": cfg.decline_min_drop},
        },
        {
            "key": "inspection_gap",
            "method": "rule",
            "description": "No observation within the interval and no open inspection task → recommend an inspection.",
            "parameters": {"inspection_gap_days": cfg.inspection_gap_days},
        },
    ]


def build_snapshots(
    db: Session, workspace_id: uuid.UUID, now: datetime, asset_ids: list[uuid.UUID] | None = None
) -> list[AssetSnapshot]:
    stmt = (
        select(BiologicalAsset, AssetState, Location.name)
        .outerjoin(AssetState, AssetState.asset_id == BiologicalAsset.id)
        .outerjoin(Location, Location.id == BiologicalAsset.location_id)
        .where(BiologicalAsset.workspace_id == workspace_id, BiologicalAsset.archived_at.is_(None))
    )
    if asset_ids is not None:
        stmt = stmt.where(BiologicalAsset.id.in_(asset_ids))
    rows = db.execute(stmt).all()
    if not rows:
        return []
    ids = [a.id for a, _, _ in rows]

    since = now - timedelta(days=HISTORY_WINDOW_DAYS)
    obs_by_asset: dict[uuid.UUID, list[Observation]] = {i: [] for i in ids}
    for o in db.scalars(
        select(Observation)
        .where(
            Observation.workspace_id == workspace_id, Observation.asset_id.in_(ids), Observation.observed_at >= since
        )
        .order_by(Observation.observed_at)
    ):
        obs_by_asset[o.asset_id].append(o)  # type: ignore[index]

    inspecting = set(
        db.scalars(
            select(Task.asset_id).where(
                Task.workspace_id == workspace_id,
                Task.asset_id.in_(ids),
                Task.type == TaskType.INSPECT.value,
                Task.status.in_([s.value for s in OPEN_TASK_STATUSES]),
            )
        )
    )

    out = []
    for asset, state, zone in rows:
        obs = obs_by_asset[asset.id]
        scored = [o for o in obs if o.health_score is not None]
        out.append(
            AssetSnapshot(
                asset_id=str(asset.id),
                label=asset.label,
                zone=zone,
                last_observed_at=as_utc(state.last_observed_at) if state and state.last_observed_at else None,
                health_history=tuple(HealthPoint(as_utc(o.observed_at), float(o.health_score)) for o in scored),  # type: ignore[arg-type]
                latest_symptoms=tuple(obs[-1].symptoms) if obs else (),
                registered_at=as_utc(asset.created_at),
                latest_health_score=state.health_score if state else None,
                latest_observation_id=str(scored[-1].id) if scored else None,
                open_issue_count=state.open_issue_count if state else 0,
                has_open_inspection_task=asset.id in inspecting,
                last_resolved_at=as_utc(state.last_resolved_at) if state and state.last_resolved_at else None,
            )
        )
    return out


def _persist(
    db: Session, workspace_id: uuid.UUID, findings: list[Finding], cfg: AgentSettings, now: datetime
) -> list[Recommendation]:
    if not findings:
        return []
    keys = [f.dedupe_key for f in findings]
    open_keys = set(
        db.scalars(
            select(Recommendation.dedupe_key).where(
                Recommendation.workspace_id == workspace_id,
                Recommendation.dedupe_key.in_(keys),
                Recommendation.status == RecommendationStatus.OPEN.value,
            )
        )
    )
    cutoff = now - timedelta(days=cfg.dismiss_suppress_days)
    suppressed = {
        k
        for k, decided in db.execute(
            select(Recommendation.dedupe_key, Recommendation.decided_at).where(
                Recommendation.workspace_id == workspace_id,
                Recommendation.dedupe_key.in_(keys),
                Recommendation.status == RecommendationStatus.DISMISSED.value,
            )
        )
        if decided is not None and as_utc(decided) >= cutoff
    }
    created: list[Recommendation] = []
    for f in findings:
        if f.dedupe_key in open_keys or f.dedupe_key in suppressed:
            continue
        rec = Recommendation(
            workspace_id=workspace_id,
            rule_key=f.rule_key,
            method=f.method,
            asset_id=uuid.UUID(f.subject_ids[0]),
            dedupe_key=f.dedupe_key,
            title=f.title,
            explanation=f.explanation,
            evidence={"evaluated_at": now.isoformat(), "inputs": f.explanation},
            proposed_action={k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in f.proposed_action.items()},
            severity=f.severity,
        )
        try:
            with db.begin_nested():  # a concurrent run inserting the same open key loses gracefully
                db.add(rec)
                db.flush()
        except IntegrityError:
            continue
        created.append(rec)
    return created


def evaluate(
    db: Session, ctx: WorkspaceContext, *, asset_ids: list[uuid.UUID] | None = None, now: datetime | None = None
) -> tuple[int, list[Recommendation]]:
    """Evaluate the workspace (or specific assets). Returns (assets evaluated, recommendations newly created).
    Does not commit: the caller owns the transaction."""
    now = now or utcnow()
    db.flush()  # see this transaction's pending observations/issues/tasks (sessions use autoflush=False)
    cfg = AgentSettings.from_workspace(ctx.workspace.settings)
    snapshots = build_snapshots(db, ctx.workspace_id, now, asset_ids)
    findings = run_agent(snapshots, now, rules=cfg.rules())
    return len(snapshots), _persist(db, ctx.workspace_id, findings, cfg, now)
