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
from app.modules.assets.models import AssetState, BiologicalAsset, HealthBand
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
    "survival": "Needs planting and loss records",
    "growth": "Needs growth records",
    "canopy": "Needs canopy measurements",
    "coverage": "Needs zone areas",
    "yield": "Estimates are planned (V2)",
    "harvest": "Estimates are planned (V2)",
    "revenue": "Needs yield and price data",
}


def _asset_conditions(ctx: WorkspaceContext, f: Filters) -> list:
    conds = [BiologicalAsset.workspace_id == ctx.workspace_id, BiologicalAsset.archived_at.is_(None)]
    if f.kind:
        conds.append(BiologicalAsset.kind == f.kind)
    if f.location_id:
        conds.append(BiologicalAsset.location_id == f.location_id)
    return conds


def _kpis(mode: str, health: HealthCounts) -> list[Kpi]:
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
        assets=AssetMetrics(total=sum(by_kind.values()), by_kind=dict(by_kind), health=health),
        work=work,
        kpis=_kpis(ctx.workspace.mode, health),
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
