"""Health and growth over time, from recorded observations only (Monitor pages, dashboard Growth KPI).

Every figure is descriptive: it summarises scores and measurements people recorded. Nothing is interpolated, smoothed
into values that were not measured, or predicted.
"""

from __future__ import annotations

import statistics
import uuid
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import Unprocessable
from app.core.timeutil import as_utc, utcnow
from app.modules.assets import lifecycle as lc
from app.modules.assets.health import health_band
from app.modules.assets.models import AssetState, BiologicalAsset
from app.modules.observations.models import Observation

from .schemas import (
    AssetChange,
    AssetGrowth,
    BandCounts,
    GrowthMonitor,
    GrowthRow,
    HealthMonitor,
    HealthWeek,
    Measurement,
    Metric,
    Unobserved,
)

METRICS: dict[str, tuple[float, float]] = {
    "height_cm": (0.1, 10_000),
    "girth_cm": (0.1, 3_000),
    "canopy_m": (0.01, 100),
}
MIN_SPAN_DAYS = 30
NOT_OBSERVED_DAYS = 30
TOP = 10


def check_measurements(data: dict) -> None:
    """Validate the measurement keys of an observation's `data` (other keys are left alone)."""
    for key, (low, high) in METRICS.items():
        if key not in data or data[key] is None:
            continue
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not (low <= float(value) <= high):
            raise Unprocessable(f"{key} must be a number from {low:g} to {high:g}", code="bad_measurement")


def _living(ctx: WorkspaceContext, kind: str | None, location_id: uuid.UUID | None) -> list:
    conds = [
        BiologicalAsset.workspace_id == ctx.workspace_id,
        BiologicalAsset.archived_at.is_(None),
        BiologicalAsset.current_stage.notin_(lc.EXIT_STAGES),
    ]
    if kind:
        conds.append(BiologicalAsset.kind == kind)
    if location_id:
        conds.append(BiologicalAsset.location_id == location_id)
    return conds


def _not_superseded(ctx: WorkspaceContext):
    return Observation.id.not_in(
        select(Observation.supersedes_id).where(
            Observation.workspace_id == ctx.workspace_id, Observation.supersedes_id.is_not(None)
        )
    )


def _monday(dt: datetime) -> datetime:
    d = as_utc(dt)
    return (d - timedelta(days=d.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


# ------------------------------------------------------------------ health


def health(
    db: Session,
    ctx: WorkspaceContext,
    *,
    weeks: int = 12,
    kind: str | None = None,
    location_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> HealthMonitor:
    if not 1 <= weeks <= 104:
        raise Unprocessable("weeks must be from 1 to 104", code="bad_weeks")
    now = now or utcnow()
    living = _living(ctx, kind, location_id)

    counts = {"healthy": 0, "at_risk": 0, "critical": 0, "no_data": 0}
    for band, n in db.execute(
        select(AssetState.health_band, func.count())
        .select_from(BiologicalAsset)
        .outerjoin(AssetState, AssetState.asset_id == BiologicalAsset.id)
        .where(*living)
        .group_by(AssetState.health_band)
    ):
        counts[band or "no_data"] += int(n)

    start = _monday(now) - timedelta(weeks=weeks - 1)
    rows = db.execute(
        select(Observation.asset_id, Observation.observed_at, Observation.health_score, BiologicalAsset.label)
        .join(
            BiologicalAsset,
            (BiologicalAsset.workspace_id == Observation.workspace_id) & (BiologicalAsset.id == Observation.asset_id),
        )
        .where(*living, Observation.health_score.is_not(None), Observation.observed_at >= start, _not_superseded(ctx))
        .order_by(Observation.observed_at)
    ).all()

    buckets: dict[datetime, list[tuple[uuid.UUID, float]]] = defaultdict(list)
    first: dict[uuid.UUID, tuple[float, datetime, str]] = {}
    latest: dict[uuid.UUID, tuple[float, datetime]] = {}
    for asset_id, at, score, label in rows:
        if asset_id is None or score is None:  # excluded by the query; keeps the types honest
            continue
        buckets[_monday(at)].append((asset_id, float(score)))
        first.setdefault(asset_id, (float(score), as_utc(at), label))
        latest[asset_id] = (float(score), as_utc(at))

    weekly = []
    for i in range(weeks):
        wk = start + timedelta(weeks=i)
        scored = buckets.get(wk, [])
        bands = [health_band(s) for _, s in scored]
        weekly.append(
            HealthWeek(
                week_start=wk,
                observations=len(scored),
                assets=len({a for a, _ in scored}),
                mean_score=round(statistics.fmean(s for _, s in scored), 1) if scored else None,
                healthy=sum(1 for b in bands if b == "healthy"),
                at_risk=sum(1 for b in bands if b == "at_risk"),
                critical=sum(1 for b in bands if b == "critical"),
            )
        )

    declining = [
        AssetChange(
            asset_id=a,
            label=first[a][2],
            first_score=first[a][0],
            first_at=first[a][1],
            latest_score=latest[a][0],
            latest_at=latest[a][1],
            change=round(latest[a][0] - first[a][0], 1),
        )
        for a in first
        if latest[a][1] > first[a][1] and latest[a][0] < first[a][0]
    ]
    declining.sort(key=lambda c: (c.change, c.label))

    cutoff = now - timedelta(days=NOT_OBSERVED_DAYS)
    last_seen = (
        select(Observation.asset_id, func.max(Observation.observed_at).label("last"))
        .where(Observation.workspace_id == ctx.workspace_id)
        .group_by(Observation.asset_id)
        .subquery()
    )
    stale_q = (
        select(BiologicalAsset.id, BiologicalAsset.label, last_seen.c.last)
        .outerjoin(last_seen, last_seen.c.asset_id == BiologicalAsset.id)
        .where(*living, (last_seen.c.last.is_(None)) | (last_seen.c.last < cutoff))
    )
    stale = db.execute(stale_q.order_by(last_seen.c.last.is_not(None), last_seen.c.last, BiologicalAsset.label)).all()
    return HealthMonitor(
        weeks=weeks,
        now=BandCounts(**counts),
        weekly=weekly,
        declining=declining[:TOP],
        not_observed_days=NOT_OBSERVED_DAYS,
        not_observed_count=len(stale),
        not_observed=[Unobserved(asset_id=i, label=label, last_observed_at=last) for i, label, last in stale[:TOP]],
    )


# ------------------------------------------------------------------ growth


def _measurement_rows(db: Session, ctx: WorkspaceContext, conds: list, since: datetime | None = None):
    q = (
        select(Observation.id, Observation.asset_id, Observation.observed_at, Observation.data)
        .join(
            BiologicalAsset,
            (BiologicalAsset.workspace_id == Observation.workspace_id) & (BiologicalAsset.id == Observation.asset_id),
        )
        .where(*conds, _not_superseded(ctx))
        .order_by(Observation.observed_at)
    )
    if since is not None:
        q = q.where(Observation.observed_at >= since)
    for oid, asset_id, at, data in db.execute(q):
        values = {k: (data or {}).get(k) for k in METRICS}
        if any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values.values()):
            yield oid, asset_id, as_utc(at), values


def asset_growth(db: Session, ctx: WorkspaceContext, asset: BiologicalAsset) -> AssetGrowth:
    conds = [BiologicalAsset.workspace_id == ctx.workspace_id, BiologicalAsset.id == asset.id]
    return AssetGrowth(
        asset_id=asset.id,
        measurements=[
            Measurement(observation_id=oid, observed_at=at, **{k: _num(v) for k, v in values.items()})
            for oid, _a, at, values in _measurement_rows(db, ctx, conds)
        ],
    )


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def growth(
    db: Session,
    ctx: WorkspaceContext,
    *,
    metric: Metric = "height_cm",
    months: int = 12,
    kind: str | None = None,
    location_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> GrowthMonitor:
    if not 1 <= months <= 60:
        raise Unprocessable("months must be from 1 to 60", code="bad_months")
    now = now or utcnow()
    since = now - timedelta(days=round(months * 30.44))
    living = _living(ctx, kind, location_id)
    series: dict[uuid.UUID, list[tuple[datetime, float]]] = defaultdict(list)
    for _oid, asset_id, at, values in _measurement_rows(db, ctx, living, since):
        v = _num(values[metric])
        if v is not None:
            series[asset_id].append((at, v))
    labels: dict[uuid.UUID, str] = {}
    kinds: dict[uuid.UUID, str] = {}
    if series:
        q = select(BiologicalAsset.id, BiologicalAsset.label, BiologicalAsset.kind).where(
            BiologicalAsset.workspace_id == ctx.workspace_id, BiologicalAsset.id.in_(series)
        )
        for aid, label, kind_ in db.execute(q):
            labels[aid], kinds[aid] = label, kind_
    rows = []
    for asset_id, points in series.items():
        (t0, v0), (t1, v1) = points[0], points[-1]
        span = (t1 - t0).days
        comparable = len(points) >= 2 and span >= MIN_SPAN_DAYS
        change = round(v1 - v0, 2) if comparable else None
        rows.append(
            GrowthRow(
                asset_id=asset_id,
                label=labels.get(asset_id, ""),
                kind=kinds.get(asset_id, ""),
                measurements=len(points),
                first=v0,
                first_at=t0,
                latest=v1,
                latest_at=t1,
                change=change,
                change_pct=round(100 * (v1 - v0) / v0, 1) if comparable and v0 > 0 else None,
                per_year=round((v1 - v0) * 365 / span, 2) if comparable and span > 0 else None,
            )
        )
    rows.sort(key=lambda r: (r.change_pct is None, -(r.change_pct or 0), r.label))
    pcts = [r.change_pct for r in rows if r.change_pct is not None]
    return GrowthMonitor(
        metric=metric,
        months=months,
        min_span_days=MIN_SPAN_DAYS,
        assets=rows,
        measured_assets=len(rows),
        comparable_assets=len(pcts),
        median_change_pct=round(statistics.median(pcts), 1) if pcts else None,
    )
