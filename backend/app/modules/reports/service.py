"""Analytics and Impact reports (ADR-068): counts and shares over RECORDED events in a period, per workspace.

Nothing here estimates, forecasts or imports outside data. Each figure is a count, a share or a median of records,
and where a figure cannot be computed the report says so instead of showing a number.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import Unprocessable
from app.core.timeutil import as_utc, utcnow
from app.modules.actions.models import ActionRecord
from app.modules.assets import lifecycle as lc
from app.modules.assets.health import health_band
from app.modules.assets.models import BiologicalAsset
from app.modules.catalog.models import Species
from app.modules.intelligence.models import Recommendation
from app.modules.issues.models import Issue
from app.modules.observations.models import Observation
from app.modules.tasks.models import OPEN_TASK_STATUSES, Task

from .schemas import (
    ActionStats,
    AgentStats,
    AnalyticsReport,
    Canopy,
    GrowthImpact,
    HealthChange,
    ImpactReport,
    IssueStats,
    Named,
    ObservationStats,
    Planting,
    SpeciesSurvival,
    Survival,
    TaskStats,
    Unavailable,
)

MEASUREMENT_KEYS = ("height_cm", "girth_cm", "canopy_m")
INDIVIDUAL_KINDS = ("tree", "plant", "shrub", "other")


def period(since: datetime | None, until: datetime | None) -> tuple[datetime, datetime]:
    end = as_utc(until) if until else utcnow()
    start = as_utc(since) if since else end - timedelta(days=365)
    if end <= start:
        raise Unprocessable("'until' must be after 'since'", code="bad_period")
    if end - start > timedelta(days=5 * 366):
        raise Unprocessable("a report covers at most five years", code="period_too_long")
    return start, end


def _in(col, start: datetime, end: datetime):
    return (col >= start) & (col < end)


def _share(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


# ------------------------------------------------------------------ analytics


def analytics(db: Session, ctx: WorkspaceContext, start: datetime, end: datetime) -> AnalyticsReport:
    ws = ctx.workspace_id
    now = utcnow()

    issues = db.execute(
        select(Issue.category, Issue.severity, Issue.opened_at, Issue.resolved_at, Issue.resolution_outcome).where(
            Issue.workspace_id == ws
        )
    ).all()
    opened = [i for i in issues if start <= as_utc(i.opened_at) < end]
    closed = [i for i in issues if i.resolved_at is not None and start <= as_utc(i.resolved_at) < end]
    days = [(as_utc(i.resolved_at) - as_utc(i.opened_at)).total_seconds() / 86400 for i in closed]
    issue_stats = IssueStats(
        opened=len(opened),
        closed=len(closed),
        still_open=sum(1 for i in issues if i.resolved_at is None),
        opened_by_category=dict(Counter(i.category for i in opened)),
        opened_by_severity=dict(Counter(i.severity for i in opened)),
        closed_by_outcome=dict(Counter(i.resolution_outcome for i in closed if i.resolution_outcome)),
        median_days_to_close=round(statistics.median(days), 1) if days else None,
    )

    tasks = db.execute(
        select(Task.type, Task.status, Task.created_at, Task.completed_at, Task.due_at).where(Task.workspace_id == ws)
    ).all()
    open_values = {s.value for s in OPEN_TASK_STATUSES}
    done = [
        t for t in tasks if t.status == "done" and t.completed_at is not None and start <= as_utc(t.completed_at) < end
    ]
    with_due = [t for t in done if t.due_at is not None]
    on_time = [t for t in with_due if as_utc(t.completed_at) <= as_utc(t.due_at)]
    task_stats = TaskStats(
        created=sum(1 for t in tasks if start <= as_utc(t.created_at) < end),
        completed=len(done),
        cancelled=sum(1 for t in tasks if t.status == "cancelled" and start <= as_utc(t.created_at) < end),
        completed_with_due_date=len(with_due),
        completed_on_time=len(on_time),
        on_time_pct=_share(len(on_time), len(with_due)),
        overdue_now=sum(
            1 for t in tasks if t.status in open_values and t.due_at is not None and as_utc(t.due_at) < now
        ),
        completed_by_type=dict(Counter(t.type for t in done)),
    )

    replaced = select(ActionRecord.supersedes_id).where(
        ActionRecord.workspace_id == ws, ActionRecord.supersedes_id.is_not(None)
    )
    actions = db.execute(
        select(ActionRecord.kind, ActionRecord.product).where(
            ActionRecord.workspace_id == ws,
            _in(ActionRecord.performed_at, start, end),
            ActionRecord.withdrawn.is_(False),
            ActionRecord.id.not_in(replaced),
        )
    ).all()
    products = Counter((a.product or "").strip() for a in actions if (a.product or "").strip())
    action_stats = ActionStats(
        recorded=len(actions),
        by_kind=dict(Counter(a.kind for a in actions)),
        top_products=[Named(name=p, count=n) for p, n in products.most_common(10)],
    )

    superseded = select(Observation.supersedes_id).where(
        Observation.workspace_id == ws, Observation.supersedes_id.is_not(None)
    )
    obs = db.execute(
        select(
            Observation.asset_id, Observation.observer_id, Observation.kind, Observation.health_score, Observation.data
        ).where(
            Observation.workspace_id == ws, _in(Observation.observed_at, start, end), Observation.id.not_in(superseded)
        )
    ).all()
    obs_stats = ObservationStats(
        recorded=len(obs),
        with_health_score=sum(1 for o in obs if o.health_score is not None),
        with_measurements=sum(1 for o in obs if any(k in (o.data or {}) for k in MEASUREMENT_KEYS)),
        assets_observed=len({o.asset_id for o in obs if o.asset_id}),
        observers=len({o.observer_id for o in obs if o.observer_id}),
        by_kind=dict(Counter(o.kind for o in obs)),
    )

    recs = db.execute(
        select(
            Recommendation.status, Recommendation.created_at, Recommendation.decided_at, Recommendation.outcome
        ).where(Recommendation.workspace_id == ws)
    ).all()
    created = [r for r in recs if start <= as_utc(r.created_at) < end]
    agent = AgentStats(
        suggested=len(created),
        accepted=sum(1 for r in created if r.status == "accepted"),
        dismissed=sum(1 for r in created if r.status == "dismissed"),
        expired=sum(1 for r in created if r.status == "expired"),
        open_now=sum(1 for r in recs if r.status == "open"),
        outcomes=dict(Counter(r.outcome for r in created if r.outcome)),
    )
    return AnalyticsReport(
        since=start,
        until=end,
        issues=issue_stats,
        tasks=task_stats,
        actions=action_stats,
        observations=obs_stats,
        agent=agent,
    )


# ------------------------------------------------------------------ impact


def impact(db: Session, ctx: WorkspaceContext, start: datetime, end: datetime) -> ImpactReport:
    ws = ctx.workspace_id
    assets = db.execute(
        select(
            BiologicalAsset.id,
            BiologicalAsset.kind,
            BiologicalAsset.tracking_mode,
            BiologicalAsset.current_stage,
            BiologicalAsset.estimated_count,
            BiologicalAsset.planted_at,
            BiologicalAsset.created_at,
            Species.common_name,
        )
        .outerjoin(Species, Species.id == BiologicalAsset.species_id)
        .where(BiologicalAsset.workspace_id == ws, BiologicalAsset.archived_at.is_(None))
    ).all()
    individual = [a for a in assets if a.tracking_mode == "individual"]
    batches = [a for a in assets if a.tracking_mode == "population"]
    registered = [a for a in individual if start <= as_utc(a.created_at) < end]
    new_batches = [a for a in batches if start <= as_utc(a.created_at) < end]

    def planted_in(a) -> bool:
        if a.planted_at is None:
            return False
        p = datetime.combine(a.planted_at, datetime.min.time(), tzinfo=UTC)
        return start <= p < end

    planting = Planting(
        registered=len(registered),
        planted=sum(1 for a in individual if planted_in(a)),
        batches_registered=len(new_batches),
        plants_in_batches=sum(a.estimated_count or 0 for a in new_batches),
        by_species=[Named(name=n, count=c) for n, c in Counter(a.common_name or "—" for a in registered).most_common()],
    )

    # survival: a snapshot of the registry, like the dashboard KPI (removed and replaced are not losses)
    by_sp: dict[str, list[int]] = {}
    for a in individual:
        if a.current_stage in lc.BIOLOGICAL_LOSS_STAGES:
            by_sp.setdefault(a.common_name or "—", [0, 0])[1] += 1
        elif not lc.is_exit(a.current_stage):
            by_sp.setdefault(a.common_name or "—", [0, 0])[0] += 1
    alive = sum(v[0] for v in by_sp.values())
    dead = sum(v[1] for v in by_sp.values())
    survival = Survival(
        alive=alive,
        dead=dead,
        rate=_share(alive, alive + dead),
        by_species=sorted(
            (
                SpeciesSurvival(species=s, alive=v[0], dead=v[1], rate=_share(v[0], v[0] + v[1]))
                for s, v in by_sp.items()
            ),
            key=lambda r: (-(r.alive + r.dead), r.species),
        ),
    )

    # health: latest score before the period vs latest score up to its end, same living assets on both sides
    living = {a.id for a in assets if not lc.is_exit(a.current_stage)}
    superseded = select(Observation.supersedes_id).where(
        Observation.workspace_id == ws, Observation.supersedes_id.is_not(None)
    )
    scores = db.execute(
        select(Observation.asset_id, Observation.observed_at, Observation.health_score)
        .where(
            Observation.workspace_id == ws,
            Observation.health_score.is_not(None),
            Observation.observed_at < end,
            Observation.id.not_in(superseded),
        )
        .order_by(Observation.observed_at)
    ).all()
    before: dict = {}
    at_end: dict = {}
    for asset_id, at, score in scores:
        if asset_id not in living:
            continue
        at_end[asset_id] = score
        if as_utc(at) < start:
            before[asset_id] = score
    both = [a for a in before if a in at_end]
    health = HealthChange(
        assets_compared=len(both),
        healthy_share_start=_share(sum(1 for a in both if health_band(before[a]) == "healthy"), len(both)),
        healthy_share_end=_share(sum(1 for a in both if health_band(at_end[a]) == "healthy"), len(both)),
    )

    from app.modules.monitor import service as monitor

    months = max(1, min(60, round((end - start).days / 30.44)))
    g = monitor.growth(db, ctx, metric="height_cm", months=months, now=end)
    growth = GrowthImpact(comparable_assets=g.comparable_assets, median_height_change_pct=g.median_change_pct)

    canopy_latest: dict = {}
    for asset_id, data in db.execute(
        select(Observation.asset_id, Observation.data)
        .where(Observation.workspace_id == ws, Observation.observed_at < end, Observation.id.not_in(superseded))
        .order_by(Observation.observed_at)
    ):
        width = (data or {}).get("canopy_m")
        if asset_id in living and isinstance(width, (int, float)) and not isinstance(width, bool) and width > 0:
            canopy_latest[asset_id] = float(width)
    area = sum(math.pi * (w / 2) ** 2 for w in canopy_latest.values())
    canopy = Canopy(trees_measured=len(canopy_latest), area_m2=round(area, 1) if canopy_latest else None)

    return ImpactReport(
        since=start,
        until=end,
        planting=planting,
        survival=survival,
        health=health,
        growth=growth,
        canopy=canopy,
        coverage=Unavailable(reason="Needs zone areas: the area of each zone is not recorded yet"),
    )
