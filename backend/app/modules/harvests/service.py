"""Recording and reading what was harvested (ADR-056)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import Conflict, NotFound, Unprocessable
from app.core.timeutil import as_utc, utcnow
from app.modules.assets import lifecycle as lc
from app.modules.assets.models import BiologicalAsset
from app.modules.audit import service as audit

from .models import MASS_TO_TONNES, HarvestRecord
from .schemas import (
    AssetHarvests,
    AssetTotals,
    HarvestCorrect,
    HarvestCreate,
    HarvestOut,
    HarvestOverview,
    HarvestRow,
    HarvestTotals,
    MonthTotals,
)

FUTURE_TOLERANCE = timedelta(minutes=5)
HISTORY_LIMIT = 500


def _when(asset: BiologicalAsset, value: datetime | None, default: datetime) -> datetime:
    harvested_at = as_utc(value) if value else default
    if harvested_at > utcnow() + FUTURE_TOLERANCE:
        raise Unprocessable("harvested_at cannot be in the future", code="harvested_in_future")
    if asset.planted_at is not None:
        planted = datetime.combine(asset.planted_at, datetime.min.time(), tzinfo=UTC)
        if harvested_at < planted:
            raise Unprocessable(
                f"harvested_at cannot be before the planting date ({asset.planted_at.isoformat()})",
                code="harvested_before_planting",
            )
    return harvested_at


def _replacements(db: Session, ctx: WorkspaceContext, asset_id: uuid.UUID) -> dict[uuid.UUID, uuid.UUID]:
    """{superseded record id: id of the correction that replaced it} for this asset."""
    rows = db.execute(
        select(HarvestRecord.supersedes_id, HarvestRecord.id).where(
            HarvestRecord.workspace_id == ctx.workspace_id,
            HarvestRecord.asset_id == asset_id,
            HarvestRecord.supersedes_id.is_not(None),
        )
    )
    return {old: new for old, new in rows}  # type: ignore[misc]


def _out(r: HarvestRecord, replaced_by: dict[uuid.UUID, uuid.UUID]) -> HarvestOut:
    effective = r.id not in replaced_by
    return HarvestOut(
        id=r.id,
        asset_id=r.asset_id,
        harvested_at=r.harvested_at,
        quantity=r.quantity,
        unit=r.unit,
        grade=r.grade,
        note=r.note,
        supersedes_id=r.supersedes_id,
        superseded_by=replaced_by.get(r.id),
        effective=effective,
        withdrawn=effective and r.supersedes_id is not None and r.quantity == 0,
        recorded_by=r.recorded_by,
        recorded_at=r.created_at,
    )


def totals_of(rows: list[HarvestOut]) -> HarvestTotals:
    by_unit: dict[str, float] = {}
    live = [r for r in rows if r.effective and r.quantity > 0]
    for r in live:
        by_unit[r.unit] = round(by_unit.get(r.unit, 0.0) + r.quantity, 3)
    mass = sum(q * MASS_TO_TONNES[u] for u, q in by_unit.items() if u in MASS_TO_TONNES)
    return HarvestTotals(by_unit=by_unit, mass_tonnes=round(mass, 3), records=len(live))


def view(db: Session, ctx: WorkspaceContext, asset: BiologicalAsset) -> AssetHarvests:
    rows = db.scalars(
        select(HarvestRecord)
        .where(HarvestRecord.workspace_id == ctx.workspace_id, HarvestRecord.asset_id == asset.id)
        .order_by(HarvestRecord.harvested_at.desc(), HarvestRecord.id.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    replaced_by = _replacements(db, ctx, asset.id)
    out = [_out(r, replaced_by) for r in rows]
    return AssetHarvests(asset_id=asset.id, totals=totals_of(out), history=out)


def record(db: Session, ctx: WorkspaceContext, asset: BiologicalAsset, data: HarvestCreate) -> AssetHarvests:
    if lc.is_exit(asset.current_stage):
        raise Conflict(
            f"This asset has left the lifecycle ({asset.current_stage}); nothing can be harvested from it",
            code="asset_exited",
        )
    rec = HarvestRecord(
        workspace_id=ctx.workspace_id,
        asset_id=asset.id,
        harvested_at=_when(asset, data.harvested_at, utcnow()),
        quantity=data.quantity,
        unit=data.unit,
        grade=(data.grade or "").strip() or None,
        note=(data.note or "").strip() or None,
        recorded_by=ctx.user.id,
    )
    db.add(rec)
    db.flush()
    audit.record_ctx(
        db,
        ctx,
        "harvest.record",
        target_type="harvest",
        target_id=rec.id,
        details={"asset_id": asset.id, "quantity": rec.quantity, "unit": rec.unit},
    )
    db.commit()
    return view(db, ctx, asset)


def correct(
    db: Session, ctx: WorkspaceContext, asset: BiologicalAsset, record_id: uuid.UUID, data: HarvestCorrect
) -> AssetHarvests:
    target = db.scalar(
        select(HarvestRecord)
        .where(
            HarvestRecord.workspace_id == ctx.workspace_id,
            HarvestRecord.asset_id == asset.id,
            HarvestRecord.id == record_id,
        )
        .with_for_update()  # two simultaneous corrections of one record: the second must see the first
    )
    if target is None:
        raise NotFound("Harvest record not found", code="harvest_not_found")
    already = db.scalar(
        select(func.count())
        .select_from(HarvestRecord)
        .where(HarvestRecord.workspace_id == ctx.workspace_id, HarvestRecord.supersedes_id == target.id)
    )
    if already:
        raise Conflict(
            "This record was already corrected; correct the latest version instead", code="harvest_already_corrected"
        )
    note = data.note.strip()
    if len(note) < 10:
        raise Unprocessable("A correction needs a written reason of at least 10 characters", code="reason_required")
    rec = HarvestRecord(
        workspace_id=ctx.workspace_id,
        asset_id=asset.id,
        harvested_at=_when(asset, data.harvested_at, as_utc(target.harvested_at)),
        quantity=data.quantity,
        unit=data.unit,
        grade=(data.grade or "").strip() or None,
        note=note,
        supersedes_id=target.id,
        recorded_by=ctx.user.id,
    )
    db.add(rec)
    try:
        db.flush()
    except IntegrityError as exc:  # the database's one-correction-per-record index won a race
        db.rollback()
        raise Conflict("This record was already corrected", code="harvest_already_corrected") from exc
    audit.record_ctx(
        db,
        ctx,
        "harvest.correct",
        target_type="harvest",
        target_id=rec.id,
        details={"asset_id": asset.id, "supersedes": target.id, "quantity": rec.quantity, "unit": rec.unit},
    )
    db.commit()
    return view(db, ctx, asset)


OVERVIEW_LIMIT = 500


def _sum(rows: list[HarvestOut]) -> dict:
    t = totals_of(rows)
    return {"by_unit": t.by_unit, "mass_tonnes": t.mass_tonnes, "records": t.records}


def overview(
    db: Session, ctx: WorkspaceContext, *, since: datetime, until: datetime, asset_id: uuid.UUID | None = None
) -> HarvestOverview:
    """Effective harvests of the workspace between `since` and `until`, with totals per unit, month and asset."""
    if until <= since:
        raise Unprocessable("'until' must be after 'since'", code="bad_period")
    if until - since > timedelta(days=3 * 366):
        raise Unprocessable("the period can be at most three years", code="period_too_long")
    replaced = select(HarvestRecord.supersedes_id).where(
        HarvestRecord.workspace_id == ctx.workspace_id, HarvestRecord.supersedes_id.is_not(None)
    )
    q = (
        select(HarvestRecord, BiologicalAsset.label)
        .join(
            BiologicalAsset,
            (BiologicalAsset.workspace_id == HarvestRecord.workspace_id)
            & (BiologicalAsset.id == HarvestRecord.asset_id),
        )
        .where(
            HarvestRecord.workspace_id == ctx.workspace_id,
            HarvestRecord.harvested_at >= since,
            HarvestRecord.harvested_at < until,
            HarvestRecord.quantity > 0,
            HarvestRecord.id.not_in(replaced),
        )
        .order_by(HarvestRecord.harvested_at.desc(), HarvestRecord.id.desc())
    )
    if asset_id:
        q = q.where(HarvestRecord.asset_id == asset_id)
    rows = db.execute(q).all()
    outs = [(_out(r, {}), label) for r, label in rows]
    every = [o for o, _ in outs]
    months: dict[str, list[HarvestOut]] = {}
    assets: dict[uuid.UUID, tuple[str, list[HarvestOut]]] = {}
    for o, label in outs:
        months.setdefault(as_utc(o.harvested_at).strftime("%Y-%m"), []).append(o)
        assets.setdefault(o.asset_id, (label, []))[1].append(o)
    by_asset = [AssetTotals(asset_id=aid, asset_label=label, **_sum(group)) for aid, (label, group) in assets.items()]
    by_asset.sort(key=lambda a: (-a.mass_tonnes, -a.records, a.asset_label))
    return HarvestOverview(
        since=since,
        until=until,
        totals=totals_of(every),
        by_month=[MonthTotals(month=m, **_sum(group)) for m, group in sorted(months.items())],
        by_asset=by_asset,
        records=[HarvestRow(**o.model_dump(), asset_label=label) for o, label in outs[:OVERVIEW_LIMIT]],
        truncated=len(outs) > OVERVIEW_LIMIT,
    )


def window_totals(
    db: Session, ctx: WorkspaceContext, scope: list, since: datetime
) -> tuple[dict[str, float], int, int]:
    """Effective harvest totals since a date, for the dashboard: (total per unit, number of WEIGHT records, number of
    distinct assets those weights came from). The two counts describe the figure that is actually summed (kg and t).
    `scope` is the dashboard's asset conditions without the lifecycle filter, so produce from an asset that later
    left the lifecycle still counts."""
    replaced = select(HarvestRecord.supersedes_id).where(
        HarvestRecord.workspace_id == ctx.workspace_id, HarvestRecord.supersedes_id.is_not(None)
    )
    effective = (
        *scope,
        HarvestRecord.harvested_at >= since,
        HarvestRecord.quantity > 0,
        HarvestRecord.id.not_in(replaced),
    )
    join = (BiologicalAsset.workspace_id == HarvestRecord.workspace_id) & (BiologicalAsset.id == HarvestRecord.asset_id)
    rows = db.execute(
        select(HarvestRecord.unit, func.sum(HarvestRecord.quantity), func.count())
        .join(BiologicalAsset, join)
        .where(*effective)
        .group_by(HarvestRecord.unit)
    ).all()
    by_unit = {unit: round(float(total), 3) for unit, total, _n in rows}
    weight_records = sum(n for unit, _t, n in rows if unit in MASS_TO_TONNES)
    weight_assets = db.scalar(
        select(func.count(func.distinct(HarvestRecord.asset_id)))
        .join(BiologicalAsset, join)
        .where(*effective, HarvestRecord.unit.in_(tuple(MASS_TO_TONNES)))
    )
    return by_unit, weight_records, int(weight_assets or 0)
