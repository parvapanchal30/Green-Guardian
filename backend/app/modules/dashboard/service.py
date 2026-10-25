"""Dashboard read model.

One backend query set builds every figure (a handful of aggregate statements: the count does not grow with the amount
of data), and one response shape serves both operating modes; the mode only selects the KPI definitions and labels.
No list is ever fetched to be summed in the browser.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.timeutil import utcnow
from app.modules.assets import lifecycle as lc
from app.modules.assets.models import AssetState, BiologicalAsset, HealthBand
from app.modules.harvests import service as harvests
from app.modules.harvests.models import MASS_TO_TONNES
from app.modules.intelligence.models import Recommendation, RecommendationStatus
from app.modules.intelligence.runner import AgentSettings
from app.modules.issues.models import Issue, IssueStatusHistory
from app.modules.observations.models import Observation
from app.modules.tasks.models import OPEN_TASK_STATUSES, Task, TaskStatusHistory

from .schemas import Activity, AssetMetrics, Dashboard, Filters, HealthCounts, Kpi, WorkMetrics

ACTIVITY_LIMIT = 10
SEVERITIES = ("critical", "high", "medium", "low")

# KPI definitions per operating mode (docs/PRD.md section 5). Same machinery for both modes.
KPI_DEFS: dict[str, list[tuple[str, str, str]]] = {
    "green_management": [
        ("survival", "Survival", "%"),
        ("health", "Health", "%"),
        ("growth", "Growth", "%"),
        ("canopy", "Canopy", "%"),
        ("coverage", "Coverage", "%"),
    ],
    "agricultural_production": [
        ("growth", "Growth", "%"),
        ("health", "Health", "%"),
        ("yield", "Yield", "t"),
        ("harvest", "Harvest", ""),
        ("revenue", "Revenue", ""),
    ],
}
NOT_COMPUTABLE = {
    "survival": "No individually tracked assets yet",
    "growth": "Needs two height measurements of an asset at least 30 days apart",
    "canopy": "Needs canopy measurements",
    "coverage": "Needs zone areas",
    "yield": "No harvests recorded in the last 12 months",
    "harvest": "Estimates are planned (V2)",
    "revenue": "Needs yield and price data",
}


def _scope_conditions(ctx: WorkspaceContext, f: Filters) -> list:
    """Every non-archived asset in scope, whatever its lifecycle stage."""
    conds = [BiologicalAsset.workspace_id == ctx.workspace_id, BiologicalAsset.archived_at.is_(None)]
    if f.kind:
        conds.append(BiologicalAsset.kind == f.kind)
    if f.location_id:
        conds.append(BiologicalAsset.location_id == f.location_id)
    return conds


def _asset_conditions(ctx: WorkspaceContext, f: Filters) -> list:
    """ACTIVE assets: an asset that has left the lifecycle (dead, removed...) is not inspected, counted or scored."""
    return [*_scope_conditions(ctx, f), BiologicalAsset.current_stage.notin_(lc.EXIT_STAGES)]


def _survival(stages: dict[tuple[str, str], int]) -> Kpi:
    """Current-registry survival of INDIVIDUALLY tracked assets: alive / (alive + recorded dead). Removed and replaced
    assets are management decisions with no recorded cause, so they are left out of both sides; populations (batches)
    are left out because partial losses are not recorded. It is a snapshot of the registry, not cohort survival at a
    given age."""
    individual = {stage: n for (tracking, stage), n in stages.items() if tracking == "individual"}
    lost = sum(individual.get(s, 0) for s in lc.BIOLOGICAL_LOSS_STAGES)
    alive = sum(n for stage, n in individual.items() if not lc.is_exit(stage))
    tracked = alive + lost
    if not tracked:
        return Kpi(key="survival", label="Survival", available=False, reason=NOT_COMPUTABLE["survival"])
    return Kpi(
        key="survival",
        label="Survival",
        available=True,
        unit="%",
        value=round(100 * alive / tracked, 1),
        basis=(
            f"{alive} alive of {tracked} individually tracked assets that are alive or recorded dead "
            "(removed and replaced assets are not counted; batches are not included)"
        ),
    )


def _harvest(stages: dict[tuple[str, str], int]) -> Kpi:
    """How many ACTIVE assets are in the harvest or post-harvest stage: a count of recorded stages, not an estimate."""
    active = sum(n for (_t, stage), n in stages.items() if not lc.is_exit(stage))
    if not active:
        return Kpi(key="harvest", label="Harvest", available=False, reason="No active assets yet")
    at_harvest = sum(n for (_t, stage), n in stages.items() if stage in lc.HARVEST_STAGES)
    return Kpi(
        key="harvest",
        label="Harvest",
        available=True,
        unit="assets",
        value=float(at_harvest),
        basis=(
            f"{at_harvest} of {active} active assets are in the harvest or post-harvest stage "
            "(recorded stages, not a forecast)"
        ),
    )


YIELD_WINDOW = timedelta(days=365)


def _yield(by_unit: dict[str, float], records: int, assets: int) -> Kpi:
    """Recorded harvest MASS over the last 12 months, in tonnes. It is a sum of what people recorded, not an estimate,
    and not per area (areas are not recorded). Counts and litres cannot be added to a weight, so they are named in the
    basis instead of being converted or ignored silently."""
    mass = sum(q * MASS_TO_TONNES[u] for u, q in by_unit.items() if u in MASS_TO_TONNES)
    others = {u: q for u, q in by_unit.items() if u not in MASS_TO_TONNES}
    if not mass:
        if others:
            return Kpi(
                key="yield",
                label="Yield",
                available=False,
                reason="Harvests are recorded in counts or litres only, which cannot be added to a weight",
            )
        return Kpi(key="yield", label="Yield", available=False, reason=NOT_COMPUTABLE["yield"])
    extra = (
        "; also recorded, not included: " + ", ".join(f"{q:g} {u}" for u, q in sorted(others.items())) if others else ""
    )
    return Kpi(
        key="yield",
        label="Yield",
        available=True,
        unit="t",
        value=round(mass, 3),
        basis=(
            f"{records} recorded harvest{'s' if records != 1 else ''} from {assets} asset{'s' if assets != 1 else ''} "
            f"in the last 12 months (weights only, not per area){extra}"
        ),
    )


def _growth(db: Session, ctx: WorkspaceContext, filters: Filters) -> Kpi:
    """Median height change over the last 12 months, among living assets with two height measurements at least 30
    days apart. A comparison of recorded measurements, never an estimate of unmeasured growth."""
    from app.modules.monitor import service as monitor

    g = monitor.growth(db, ctx, metric="height_cm", months=12, kind=filters.kind, location_id=filters.location_id)
    if g.median_change_pct is None:
        return Kpi(key="growth", label="Growth", available=False, reason=NOT_COMPUTABLE["growth"])
    return Kpi(
        key="growth",
        label="Growth",
        available=True,
        unit="%",
        value=g.median_change_pct,
        basis=(
            f"median height change of {g.comparable_assets} assets measured twice or more at least "
            f"{g.min_span_days} days apart in the last 12 months ({g.measured_assets} measured in all)"
        ),
    )


def _kpis(
    mode: str,
    health: HealthCounts,
    stages: dict[tuple[str, str], int],
    yield_kpi: Kpi | None = None,
    growth_kpi: Kpi | None = None,
) -> list[Kpi]:
    observed = health.healthy + health.at_risk + health.critical
    out = []
    for key, label, unit in KPI_DEFS.get(mode, KPI_DEFS["green_management"]):
        if key == "health":
            if observed:
                out.append(
                    Kpi(
                        key=key,
                        label=label,
                        available=True,
                        unit=unit,
                        value=round(100 * health.healthy / observed, 1),
                        basis=f"{health.healthy} healthy of {observed} assets with a recorded health score",
                    )
                )
            else:
                out.append(Kpi(key=key, label=label, available=False, reason="No health scores recorded yet"))
        elif key == "survival":
            out.append(_survival(stages))
        elif key == "harvest":
            out.append(_harvest(stages))
        elif key == "yield" and yield_kpi is not None:
            out.append(yield_kpi)
        elif key == "growth" and growth_kpi is not None:
            out.append(growth_kpi)
        else:
            out.append(Kpi(key=key, label=label, available=False, reason=NOT_COMPUTABLE[key]))
    return out


def build(db: Session, ctx: WorkspaceContext, filters: Filters) -> Dashboard:
    now = utcnow()
    ws = ctx.workspace_id
    conds = _asset_conditions(ctx, filters)
    scoped = bool(filters.kind or filters.location_id)
    scope = select(BiologicalAsset.id).where(*conds)
    interval_days = AgentSettings.from_workspace(ctx.workspace.settings).inspection_gap_days
    cutoff = now - timedelta(days=interval_days)

    # 1) assets by kind and health band: one grouped query
    by_kind: dict[str, int] = defaultdict(int)
    band_counts = {b.value: 0 for b in HealthBand}
    unknown = 0
    for kind, band, n in db.execute(
        select(BiologicalAsset.kind, AssetState.health_band, func.count())
        .select_from(BiologicalAsset)
        .outerjoin(AssetState, AssetState.asset_id == BiologicalAsset.id)
        .where(*conds)
        .group_by(BiologicalAsset.kind, AssetState.health_band)
    ):
        by_kind[kind] += n
        if band in band_counts:
            band_counts[band] += n
        else:
            unknown += n
    health = HealthCounts(
        healthy=band_counts["healthy"],
        at_risk=band_counts["at_risk"],
        critical=band_counts["critical"],
        unknown=unknown,
    )

    # 1b) assets by (tracking mode, lifecycle stage), exited ones included: feeds survival, harvest and the exited count
    stages: dict[tuple[str, str], int] = defaultdict(int)
    for tracking, stage, n in db.execute(
        select(BiologicalAsset.tracking_mode, BiologicalAsset.current_stage, func.count())
        .where(*_scope_conditions(ctx, filters))
        .group_by(BiologicalAsset.tracking_mode, BiologicalAsset.current_stage)
    ):
        stages[(tracking, stage)] += n
    exited = sum(n for (_t, stage), n in stages.items() if lc.is_exit(stage))

    # 1c) recorded harvest over the last 12 months (agricultural workspaces only; one grouped query)
    yield_kpi = None
    if ctx.workspace.mode == "agricultural_production":
        yield_kpi = _yield(*harvests.window_totals(db, ctx, _scope_conditions(ctx, filters), now - YIELD_WINDOW))

    # 2) open issues by severity
    issue_q = select(Issue.severity, func.count()).where(Issue.workspace_id == ws, Issue.resolved_at.is_(None))
    if scoped:
        issue_q = issue_q.where(Issue.asset_id.in_(scope))
    sev = {s: 0 for s in SEVERITIES}
    for severity, n in db.execute(issue_q.group_by(Issue.severity)):
        sev[severity] = n

    # 3) tasks: open / overdue / due within 7 days, in one statement
    is_open = Task.status.in_([s.value for s in OPEN_TASK_STATUSES])
    task_q = select(
        func.count().filter(is_open),
        func.count().filter(and_(is_open, Task.due_at.is_not(None), Task.due_at < now)),
        func.count().filter(
            and_(is_open, Task.due_at.is_not(None), Task.due_at >= now, Task.due_at < now + timedelta(days=7))
        ),
    ).where(Task.workspace_id == ws)
    if scoped:
        task_q = task_q.where(Task.asset_id.in_(scope))
    open_tasks, overdue, due_soon = db.execute(task_q).one()

    # 4) inspections due: not observed within the interval (never-observed assets count from registration)
    due_q = (
        select(func.count())
        .select_from(BiologicalAsset)
        .outerjoin(AssetState, AssetState.asset_id == BiologicalAsset.id)
        .where(
            *conds,
            or_(
                AssetState.last_observed_at < cutoff,
                and_(AssetState.last_observed_at.is_(None), BiologicalAsset.created_at < cutoff),
            ),
        )
    )
    inspections_due = db.scalar(due_q) or 0

    # 5) open recommendations awaiting a decision
    rec_q = (
        select(func.count())
        .select_from(Recommendation)
        .where(Recommendation.workspace_id == ws, Recommendation.status == RecommendationStatus.OPEN.value)
    )
    if scoped:
        rec_q = rec_q.where(Recommendation.asset_id.in_(scope))
    open_recs = db.scalar(rec_q) or 0

    work = WorkMetrics(
        open_issues=sum(sev.values()),
        open_issues_by_severity=sev,
        open_tasks=open_tasks,
        overdue_tasks=overdue,
        tasks_due_next_7_days=due_soon,
        inspections_due=inspections_due,
        inspection_interval_days=interval_days,
        open_recommendations=open_recs,
    )
    return Dashboard(
        mode=ctx.workspace.mode,
        as_of=now,
        filters=filters,
        assets=AssetMetrics(total=sum(by_kind.values()), by_kind=dict(by_kind), health=health, exited=exited),
        work=work,
        kpis=_kpis(ctx.workspace.mode, health, stages, yield_kpi, _growth(db, ctx, filters)),
        recent_activity=_recent_activity(db, ctx, scope if scoped else None),
    )


def _recent_activity(db: Session, ctx: WorkspaceContext, scope) -> list[Activity]:
    """Latest observations, issue changes and task changes: three small bounded queries, merged."""
    ws, n = ctx.workspace_id, ACTIVITY_LIMIT
    items: list[Activity] = []

    obs_q = (
        select(Observation, BiologicalAsset.label)
        .join(
            BiologicalAsset,
            (BiologicalAsset.workspace_id == Observation.workspace_id) & (BiologicalAsset.id == Observation.asset_id),
        )
        .where(Observation.workspace_id == ws)
    )
    if scope is not None:
        obs_q = obs_q.where(Observation.asset_id.in_(scope))
    for o, label in db.execute(obs_q.order_by(Observation.observed_at.desc()).limit(n)):
        bits = [
            f"health {o.health_score:g}" if o.health_score is not None else None,
            ", ".join(o.symptoms) or None,
            o.notes,
        ]
        items.append(
            Activity(
                at=o.observed_at,
                type="observation",
                ref_id=o.id,
                asset_id=o.asset_id,
                key=None,
                title=f"Observation: {label}",
                detail=" · ".join(b for b in bits if b) or None,
            )
        )

    ih_q = (
        select(IssueStatusHistory, Issue.key, Issue.title, Issue.asset_id)
        .join(
            Issue, (Issue.workspace_id == IssueStatusHistory.workspace_id) & (Issue.id == IssueStatusHistory.issue_id)
        )
        .where(IssueStatusHistory.workspace_id == ws)
    )
    if scope is not None:
        ih_q = ih_q.where(Issue.asset_id.in_(scope))
    for h, key, title, asset_id in db.execute(ih_q.order_by(IssueStatusHistory.at.desc()).limit(n)):
        what = (
            f"opened as {h.to_state}"
            if h.from_state is None
            else (f"{h.from_state} → {h.to_state}" if h.from_state != h.to_state else "updated")
        )
        items.append(
            Activity(
                at=h.at,
                type="issue",
                ref_id=h.issue_id,
                asset_id=asset_id,
                key=key,
                title=f"{key} {title}",
                detail=what + (f" — {h.note}" if h.note else ""),
            )
        )

    th_q = (
        select(TaskStatusHistory, Task.key, Task.title, Task.asset_id)
        .join(Task, (Task.workspace_id == TaskStatusHistory.workspace_id) & (Task.id == TaskStatusHistory.task_id))
        .where(TaskStatusHistory.workspace_id == ws)
    )
    if scope is not None:
        th_q = th_q.where(Task.asset_id.in_(scope))
    for th, key, title, asset_id in db.execute(th_q.order_by(TaskStatusHistory.at.desc()).limit(n)):
        what = (
            f"created as {th.to_status}"
            if th.from_status is None
            else (f"{th.from_status} → {th.to_status}" if th.from_status != th.to_status else "updated")
        )
        items.append(
            Activity(
                at=th.at,
                type="task",
                ref_id=th.task_id,
                asset_id=asset_id,
                key=key,
                title=f"{key} {title}",
                detail=what + (f" — {th.note}" if th.note else ""),
            )
        )

    items.sort(key=lambda a: a.at, reverse=True)
    return items[:n]


__all__ = ["build", "Filters", "uuid"]
