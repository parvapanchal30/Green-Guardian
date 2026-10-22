"""Runs the Botanical Operations Agent (rules) for a workspace and persists its recommendations.

Deterministic and explainable: it reads recorded data, applies thresholds, and writes `Recommendation` rows that a
person accepts or dismisses. It never creates issues or tasks by itself, and it produces no ML or LLM output.

Weather reaches the agent only through the `WeatherContextProvider` port, and only for assets that have an open
watering task (so a workspace without irrigation work causes no weather requests).
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.timeutil import as_utc, utcnow
from app.modules.assets.lifecycle import EXIT_STAGES
from app.modules.assets.models import AssetState, BiologicalAsset
from app.modules.issues.models import Issue, IssueStatusHistory
from app.modules.locations.models import Location
from app.modules.observations.models import Observation
from app.modules.tasks.models import OPEN_TASK_STATUSES, Task, TaskStatus, TaskType

from .models import Recommendation, RecommendationStatus
from .ports import WeatherContext, WeatherContextProvider
from .rules.base import RULE_VERSIONS, AssetSnapshot, Finding, HealthPoint, Rule, WaterTask
from .rules.irrigation import IrrigationDeferral
from .rules.mvp_rules import CriticalHealth, HealthDecline, InspectionGap, run_agent_detailed

HISTORY_WINDOW_DAYS = 30
# Recorded symptoms and issue categories that point at a plant short of water: an irrigation-deferral suggestion is
# withheld for such an asset whatever the forecast says.
WATER_STRESS_SYMPTOMS = frozenset(
    {"wilting", "wilt", "drooping", "leaf_scorch", "scorch", "leaf_curl", "drought_stress", "water_stress", "dry_soil"}
)
WATER_STRESS_CATEGORIES = frozenset({"water_stress", "irrigation_failure"})
WEATHER_GRID_DEGREES = 0.1  # assets within ~11 km share one forecast request


@dataclass(frozen=True)
class AgentSettings:
    """Per-workspace configuration, stored under `workspace.settings["agent"]`; defaults apply for anything missing
    or malformed. Parameters are recorded on every run (`agent_runs.rules`), so what produced a suggestion is kept."""

    inspection_gap_days: int = 21
    critical_health_below: float = 40.0
    decline_window_days: int = 14
    decline_min_drop: float = 15.0
    dismiss_suppress_days: int = 7
    # scheduling
    schedule_enabled: bool = True
    schedule_interval_hours: int = 24
    # irrigation deferral (advisory, forecast-based; see rules/irrigation.py for what it does and does not know)
    irrigation_defer_enabled: bool = True
    irrigation_min_rain_mm: float = 5.0
    irrigation_min_probability_pct: float = 70.0
    irrigation_defer_hours: int = 24
    irrigation_lookahead_hours: int = 24

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
            ("schedule_interval_hours", int),
            ("irrigation_min_rain_mm", float),
            ("irrigation_min_probability_pct", float),
            ("irrigation_defer_hours", int),
            ("irrigation_lookahead_hours", int),
        ):
            if name in raw:
                try:
                    value = caster(raw[name])
                except (TypeError, ValueError):
                    continue  # a malformed override falls back to the default rather than breaking the agent
                if value > 0:
                    out[name] = value
        for flag in ("schedule_enabled", "irrigation_defer_enabled"):
            if isinstance(raw.get(flag), bool):
                out[flag] = raw[flag]
        return cls(**out)

    def rules(self) -> tuple[Rule, ...]:
        # Order matters: the first rule proposing an issue for an asset wins. SymptomCluster needs multi-asset issues
        # and is not wired into the workspace runner yet.
        rules: list[Rule] = [
            CriticalHealth(below=self.critical_health_below),
            HealthDecline(window_days=self.decline_window_days, min_drop=self.decline_min_drop),
            InspectionGap(max_days=self.inspection_gap_days),
        ]
        if self.irrigation_defer_enabled:
            rules.append(
                IrrigationDeferral(
                    min_rain_mm=self.irrigation_min_rain_mm,
                    min_probability_pct=self.irrigation_min_probability_pct,
                    defer_hours=self.irrigation_defer_hours,
                    lookahead_hours=self.irrigation_lookahead_hours,
                )
            )
        return tuple(rules)


def describe_rules(cfg: AgentSettings) -> list[dict]:
    rules: list[dict[str, Any]] = [
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
            "description": "Nobody has looked at the asset within the interval (no observation, completed inspection "
            "or issue activity) and no open inspection task → recommend an inspection.",
            "parameters": {"inspection_gap_days": cfg.inspection_gap_days},
        },
    ]
    if cfg.irrigation_defer_enabled:
        rules.append(
            {
                "key": "irrigation_defer",
                "method": "rule",
                "description": "A watering task is about to fall due and the forecast shows enough likely rain → "
                "suggest considering a deferral. ADVISORY and forecast-based: it does not know soil moisture, "
                "observed rainfall, species water needs or irrigation volumes, and it is withheld when the asset "
                "shows signs of water stress.",
                "parameters": {
                    "irrigation_min_rain_mm": cfg.irrigation_min_rain_mm,
                    "irrigation_min_probability_pct": cfg.irrigation_min_probability_pct,
                    "irrigation_defer_hours": cfg.irrigation_defer_hours,
                    "irrigation_lookahead_hours": cfg.irrigation_lookahead_hours,
                },
            }
        )
    for r in rules:
        r["version"] = RULE_VERSIONS[r["key"]]
    return rules


# ------------------------------------------------------------------------------------------------ snapshots


@dataclass
class SnapshotResult:
    snapshots: list[AssetSnapshot]
    weather: dict = field(default_factory=dict)  # diagnostics about the weather lookups


def _grid(lat: float, lon: float) -> tuple[float, float]:
    step = WEATHER_GRID_DEGREES
    return round(round(lat / step) * step, 4), round(round(lon / step) * step, 4)


def build_snapshots_with_context(
    db: Session,
    workspace_id: uuid.UUID,
    now: datetime,
    asset_ids: list[uuid.UUID] | None = None,
    *,
    weather: WeatherContextProvider | None = None,
) -> SnapshotResult:
    stmt = (
        select(BiologicalAsset, AssetState, Location.name, Location.latitude, Location.longitude)
        .outerjoin(AssetState, AssetState.asset_id == BiologicalAsset.id)
        .outerjoin(
            Location,
            (Location.workspace_id == BiologicalAsset.workspace_id) & (Location.id == BiologicalAsset.location_id),
        )
        # An asset that left the lifecycle (dead, removed...) is never inspected or advised on.
        .where(
            BiologicalAsset.workspace_id == workspace_id,
            BiologicalAsset.archived_at.is_(None),
            BiologicalAsset.current_stage.notin_(EXIT_STAGES),
        )
    )
    if asset_ids is not None:
        stmt = stmt.where(BiologicalAsset.id.in_(asset_ids))
    rows = db.execute(stmt).all()
    if not rows:
        return SnapshotResult([])
    ids = [r[0].id for r in rows]

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

    open_statuses = [s.value for s in OPEN_TASK_STATUSES]
    inspecting = set(
        db.scalars(
            select(Task.asset_id).where(
                Task.workspace_id == workspace_id,
                Task.asset_id.in_(ids),
                Task.type == TaskType.INSPECT.value,
                Task.status.in_(open_statuses),
            )
        )
    )
    last_inspection_done = {
        aid: as_utc(at)
        for aid, at in db.execute(
            select(Task.asset_id, func.max(Task.completed_at))
            .where(
                Task.workspace_id == workspace_id,
                Task.asset_id.in_(ids),
                Task.type == TaskType.INSPECT.value,
                Task.status == TaskStatus.DONE.value,
                Task.completed_at.is_not(None),
            )
            .group_by(Task.asset_id)
        )
        if at is not None
    }
    last_issue_activity = {
        aid: as_utc(at)
        for aid, at in db.execute(
            select(Issue.asset_id, func.max(IssueStatusHistory.at))
            .join(
                IssueStatusHistory,
                (IssueStatusHistory.workspace_id == Issue.workspace_id) & (IssueStatusHistory.issue_id == Issue.id),
            )
            .where(Issue.workspace_id == workspace_id, Issue.asset_id.in_(ids))
            .group_by(Issue.asset_id)
        )
        if at is not None and aid is not None
    }

    # irrigation context, only for assets that have an open watering task
    water_tasks: dict[uuid.UUID, list[WaterTask]] = {}
    for t in db.scalars(
        select(Task).where(
            Task.workspace_id == workspace_id,
            Task.asset_id.in_(ids),
            Task.type == TaskType.WATER.value,
            Task.status.in_(open_statuses),
        )
    ):
        water_tasks.setdefault(t.asset_id, []).append(  # type: ignore[arg-type]
            WaterTask(str(t.id), t.key, t.status, as_utc(t.due_at) if t.due_at else None)
        )
    watered_ids = list(water_tasks)
    last_watered: dict[uuid.UUID, datetime] = {}
    stress_issue_assets: set[uuid.UUID] = set()
    if watered_ids:
        last_watered = {
            aid: as_utc(at)
            for aid, at in db.execute(
                select(Task.asset_id, func.max(Task.completed_at))
                .where(
                    Task.workspace_id == workspace_id,
                    Task.asset_id.in_(watered_ids),
                    Task.type == TaskType.WATER.value,
                    Task.status == TaskStatus.DONE.value,
                    Task.completed_at.is_not(None),
                )
                .group_by(Task.asset_id)
            )
            if at is not None and aid is not None
        }
        stress_issue_assets = set(
            db.scalars(
                select(Issue.asset_id).where(
                    Issue.workspace_id == workspace_id,
                    Issue.asset_id.in_(watered_ids),
                    Issue.resolved_at.is_(None),
                    Issue.category.in_(WATER_STRESS_CATEGORIES),
                )
            )
        )

    positions: dict[uuid.UUID, tuple[float, float, str] | None] = {}
    for asset, _state, _zone, loc_lat, loc_lon in rows:
        if asset.latitude is not None and asset.longitude is not None:
            positions[asset.id] = (asset.latitude, asset.longitude, "asset")
        elif loc_lat is not None and loc_lon is not None:
            positions[asset.id] = (loc_lat, loc_lon, "location")
        else:
            positions[asset.id] = None

    contexts: dict[tuple[float, float], WeatherContext | None] = {}
    diag: dict[str, Any] = {"requested": False, "locations": 0, "unavailable": 0, "no_location": 0, "source": None}
    if weather is not None and watered_ids:
        diag["requested"] = True
        for aid in watered_ids:
            pos = positions.get(aid)
            if pos is None:
                diag["no_location"] += 1
                continue
            cell = _grid(pos[0], pos[1])
            if cell not in contexts:
                got = weather.context_for(cell[0], cell[1], now)
                contexts[cell] = got
                diag["locations"] += 1
                if got is None:
                    diag["unavailable"] += 1
                elif diag["source"] is None:
                    diag["source"] = got.source

    out = []
    for asset, state, zone, _lat, _lon in rows:
        obs = obs_by_asset[asset.id]
        scored = [o for o in obs if o.health_score is not None]
        pos = positions[asset.id]
        has_water = asset.id in water_tasks
        signs: tuple[str, ...] = ()
        if has_water:
            hits = sorted({s for s in (obs[-1].symptoms if obs else []) if s.lower() in WATER_STRESS_SYMPTOMS})
            signs = tuple(hits) + (("open water-stress issue",) if asset.id in stress_issue_assets else ())
        ctx_weather = None
        status = "not_needed"
        if has_water:
            if pos is None:
                status = "no_location"
            elif not diag["requested"]:
                status = "not_requested"
            else:
                ctx_weather = contexts.get(_grid(pos[0], pos[1]))
                status = "ok" if ctx_weather is not None else "unavailable"
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
                last_inspection_completed_at=last_inspection_done.get(asset.id),
                last_issue_activity_at=last_issue_activity.get(asset.id),
                latitude=pos[0] if pos else None,
                longitude=pos[1] if pos else None,
                position_source=pos[2] if pos else None,
                open_water_tasks=tuple(water_tasks.get(asset.id, ())),
                last_watered_at=last_watered.get(asset.id),
                water_stress_signs=signs,
                weather=ctx_weather,
                weather_status=status,
            )
        )
    return SnapshotResult(out, diag)


def build_snapshots(
    db: Session, workspace_id: uuid.UUID, now: datetime, asset_ids: list[uuid.UUID] | None = None
) -> list[AssetSnapshot]:
    return build_snapshots_with_context(db, workspace_id, now, asset_ids, weather=None).snapshots


# ------------------------------------------------------------------------------------------------ persistence


@dataclass
class Persisted:
    created: list[Recommendation] = field(default_factory=list)
    already_open: int = 0
    dismissed_recently: int = 0


def _persist(
    db: Session,
    workspace_id: uuid.UUID,
    findings: list[Finding],
    cfg: AgentSettings,
    now: datetime,
    run_id: uuid.UUID | None = None,
) -> Persisted:
    result = Persisted()
    if not findings:
        return result
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
    for f in findings:
        if f.dedupe_key in open_keys:
            result.already_open += 1
            continue
        if f.dedupe_key in suppressed:
            result.dismissed_recently += 1
            continue
        version = RULE_VERSIONS.get(f.rule_key)
        rec = Recommendation(
            workspace_id=workspace_id,
            rule_key=f.rule_key,
            rule_version=version,
            method=f.method,
            asset_id=uuid.UUID(f.subject_ids[0]),
            dedupe_key=f.dedupe_key,
            title=f.title,
            explanation=f.explanation,
            evidence={
                "evaluated_at": now.isoformat(),
                "rule": {"key": f.rule_key, "version": version},
                "inputs": f.evidence or {"summary": f.explanation},
            },
            proposed_action={k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in f.proposed_action.items()},
            severity=f.severity,
            agent_run_id=run_id,
        )
        try:
            with db.begin_nested():  # a concurrent run inserting the same open key loses gracefully
                db.add(rec)
                db.flush()
        except IntegrityError:
            result.already_open += 1
            continue
        result.created.append(rec)
    return result


def _authoritative_assets(rule_key: str, snapshots: list[AssetSnapshot], cfg: AgentSettings) -> set[str]:
    """Assets for which this rule's conclusion is trustworthy THIS run. A suggestion is only expired when the rule
    could see the situation: an irrigation suggestion is kept (not expired) while the forecast is unavailable."""
    if rule_key == "irrigation_defer" and cfg.irrigation_defer_enabled:
        return {
            s.asset_id for s in snapshots if not s.open_water_tasks or s.weather_status == "ok" or s.water_stress_signs
        }
    return {s.asset_id for s in snapshots}


def _expire_stale(
    db: Session,
    workspace_id: uuid.UUID,
    snapshots: list[AssetSnapshot],
    findings: list[Finding],
    cfg: AgentSettings,
    now: datetime,
    run_id: uuid.UUID | None,
) -> int:
    """Open suggestions whose premise no longer holds become `expired` (the asset was inspected, health recovered, the
    watering task was done or the rain forecast cleared). Suggestions are never silently deleted and never touched
    when the rule could not see the situation."""
    if not snapshots:
        return 0
    evaluated = {s.asset_id for s in snapshots}
    current = {f.dedupe_key for f in findings}
    active_rules = {r.key for r in cfg.rules()}
    expired = 0
    for rec in db.scalars(
        select(Recommendation).where(
            Recommendation.workspace_id == workspace_id,
            Recommendation.status == RecommendationStatus.OPEN.value,
            Recommendation.asset_id.in_([uuid.UUID(a) for a in evaluated]),
        )
    ):
        if rec.dedupe_key in current:
            continue
        if rec.rule_key in active_rules:
            if str(rec.asset_id) not in _authoritative_assets(rec.rule_key, snapshots, cfg):
                continue
            reason = "the condition that triggered it no longer holds"
        elif rec.rule_key == "irrigation_defer":
            reason = "irrigation advice is switched off for this workspace"
        else:
            continue  # a rule not run here (for example symptom_cluster): leave it alone
        rec.status = RecommendationStatus.EXPIRED.value
        rec.decided_at = now
        rec.evidence = {
            **(rec.evidence or {}),
            "expired": {"at": now.isoformat(), "reason": reason, "run_id": str(run_id) if run_id else None},
        }
        expired += 1
    return expired


# ------------------------------------------------------------------------------------------------ evaluation


@dataclass
class EvaluationResult:
    evaluated: int
    findings: int
    created: list[Recommendation]
    expired: int
    already_open: int
    dismissed_recently: int
    rules: list[dict]
    diagnostics: dict


def evaluate_workspace(
    db: Session,
    workspace_id: uuid.UUID,
    workspace_settings: dict | None,
    *,
    now: datetime | None = None,
    asset_ids: list[uuid.UUID] | None = None,
    weather: WeatherContextProvider | None = None,
    run_id: uuid.UUID | None = None,
) -> EvaluationResult:
    """Evaluate one workspace (or specific assets) with that workspace's own settings. Does not commit: the caller owns
    the transaction. The only workspace touched is `workspace_id`."""
    now = now or utcnow()
    db.flush()  # see this transaction's pending observations/issues/tasks (sessions use autoflush=False)
    cfg = AgentSettings.from_workspace(workspace_settings)
    # weather is only needed by the irrigation rule: a workspace that switched it off causes no provider requests
    snap = build_snapshots_with_context(
        db, workspace_id, now, asset_ids, weather=weather if cfg.irrigation_defer_enabled else None
    )
    findings, skips = run_agent_detailed(snap.snapshots, now, rules=cfg.rules())
    persisted = _persist(db, workspace_id, findings, cfg, now, run_id)
    expired = _expire_stale(db, workspace_id, snap.snapshots, findings, cfg, now, run_id)
    reasons = Counter(sk.reason for sk in skips)
    diagnostics = {
        "weather": snap.weather,
        "skipped": dict(reasons),
        "skipped_examples": [{"asset_id": s.asset_id, "rule": s.rule_key, "reason": s.reason} for s in skips[:10]],
        "already_open": persisted.already_open,
        "dismissed_recently": persisted.dismissed_recently,
    }
    return EvaluationResult(
        evaluated=len(snap.snapshots),
        findings=len(findings),
        created=persisted.created,
        expired=expired,
        already_open=persisted.already_open,
        dismissed_recently=persisted.dismissed_recently,
        rules=describe_rules(cfg),
        diagnostics=diagnostics,
    )


def evaluate(
    db: Session, ctx: WorkspaceContext, *, asset_ids: list[uuid.UUID] | None = None, now: datetime | None = None
) -> tuple[int, list[Recommendation]]:
    """Evaluate the workspace (or specific assets) inline, without weather (used when an observation is saved, which
    must stay fast). Returns (assets evaluated, recommendations newly created). Does not commit."""
    result = evaluate_workspace(db, ctx.workspace_id, ctx.workspace.settings, now=now, asset_ids=asset_ids)
    return result.evaluated, result.created
