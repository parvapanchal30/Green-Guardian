from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, manager_ctx, viewer_ctx, worker_ctx
from app.core.timeutil import as_utc, utcnow
from app.modules.assets.service import get_asset

from . import service
from .schemas import AssetHarvests, HarvestCorrect, HarvestCreate, HarvestOverview

router = APIRouter(prefix="/workspaces/{ws}/assets/{asset_id}/harvests", tags=["harvests"])
overview_router = APIRouter(prefix="/workspaces/{ws}/harvests", tags=["harvests"])


@overview_router.get("", response_model=HarvestOverview)
def harvest_overview(
    since: datetime | None = None,
    until: datetime | None = None,
    asset_id: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    """Every effective harvest of the workspace in a period (default: the last 12 months), with totals per unit, per
    month and per asset. Only kg and t are added together."""
    end = as_utc(until) if until else utcnow()
    start = as_utc(since) if since else end - timedelta(days=365)
    return service.overview(db, ctx, since=start, until=end, asset_id=asset_id)


@router.get("", response_model=AssetHarvests)
def list_harvests(asset_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)):
    """What was harvested from this asset: effective totals per unit and the full append-only history."""
    return service.view(db, ctx, get_asset(db, ctx, asset_id, include_archived=True))


@router.post("", response_model=AssetHarvests, status_code=status.HTTP_201_CREATED)
def record_harvest(
    asset_id: uuid.UUID, data: HarvestCreate, ctx: WorkspaceContext = Depends(worker_ctx), db: Session = Depends(get_db)
):
    return service.record(db, ctx, get_asset(db, ctx, asset_id), data)


@router.post("/{record_id}/correct", response_model=AssetHarvests, status_code=status.HTTP_201_CREATED)
def correct_harvest(
    asset_id: uuid.UUID,
    record_id: uuid.UUID,
    data: HarvestCorrect,
    ctx: WorkspaceContext = Depends(manager_ctx),
    db: Session = Depends(get_db),
):
    """Records are never edited: a manager replaces one with a corrected record and a reason (0 withdraws it)."""
    return service.correct(db, ctx, get_asset(db, ctx, asset_id), record_id, data)
