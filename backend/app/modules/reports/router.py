from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, viewer_ctx

from . import service
from .schemas import AnalyticsReport, ImpactReport

router = APIRouter(prefix="/workspaces/{ws}/reports", tags=["reports"])


@router.get("/analytics", response_model=AnalyticsReport)
def analytics(
    since: datetime | None = None,
    until: datetime | None = None,
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    """Issues, tasks, work, observations and agent suggestions in a period (default: the last 12 months)."""
    start, end = service.period(since, until)
    return service.analytics(db, ctx, start, end)


@router.get("/impact", response_model=ImpactReport)
def impact(
    since: datetime | None = None,
    until: datetime | None = None,
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    """Plantings, survival, health change, measured growth and calculated canopy area (default: the last 12 months)."""
    start, end = service.period(since, until)
    return service.impact(db, ctx, start, end)
