from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, viewer_ctx
from app.modules.assets.models import AssetKind

from . import service
from .schemas import Dashboard, Filters

router = APIRouter(prefix="/workspaces/{ws}/dashboard", tags=["dashboard"])


@router.get("", response_model=Dashboard)
def get_dashboard(
    location_id: uuid.UUID | None = None,
    kind: AssetKind | None = Query(default=None),
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    """Operational metrics for the workspace, optionally narrowed to one location and/or asset kind.
    One shape for both operating modes; the mode selects the KPI set."""
    return service.build(db, ctx, Filters(location_id=location_id, kind=kind.value if kind else None))
