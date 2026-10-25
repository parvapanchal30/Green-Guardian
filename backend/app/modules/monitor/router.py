from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, viewer_ctx
from app.modules.assets.models import AssetKind
from app.modules.assets.service import get_asset

from . import service
from .schemas import AssetGrowth, GrowthMonitor, HealthMonitor, Metric

router = APIRouter(prefix="/workspaces/{ws}", tags=["monitor"])


@router.get("/monitor/health", response_model=HealthMonitor)
def monitor_health(
    weeks: int = 12,
    kind: AssetKind | None = None,
    location_id: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    """Health over time from recorded scores: current bands, weekly figures, declines, and assets not looked at."""
    return service.health(db, ctx, weeks=weeks, kind=kind.value if kind else None, location_id=location_id)


@router.get("/monitor/growth", response_model=GrowthMonitor)
def monitor_growth(
    metric: Metric = "height_cm",
    months: int = 12,
    kind: AssetKind | None = None,
    location_id: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    """Growth between recorded measurements (height, trunk girth or canopy width) per asset, over a period."""
    return service.growth(
        db, ctx, metric=metric, months=months, kind=kind.value if kind else None, location_id=location_id
    )


@router.get("/assets/{asset_id}/growth", response_model=AssetGrowth)
def asset_growth(asset_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)):
    """Every measurement recorded for this asset, oldest first."""
    return service.asset_growth(db, ctx, get_asset(db, ctx, asset_id, include_archived=True))
