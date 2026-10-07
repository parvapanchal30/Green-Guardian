from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, manager_ctx, viewer_ctx, worker_ctx
from app.core.pagination import Page, PageParams, page_params

from . import service
from .models import AssetKind, HealthBand
from .schemas import AssetCreate, AssetOut, AssetUpdate, TimelineEvent

router = APIRouter(prefix="/workspaces/{ws}/assets", tags=["assets"])


@router.get("", response_model=Page[AssetOut])
def list_assets(
    kind: AssetKind | None = None,
    location_id: uuid.UUID | None = None,
    health_band: HealthBand | None = None,
    q: str | None = None,
    has_open_issue: bool | None = None,
    page: PageParams = Depends(page_params),
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    return service.list_assets(
        db, ctx, page, kind=kind, location_id=location_id, health_band=health_band, q=q, has_open_issue=has_open_issue
    )


@router.post("", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
def create_asset(data: AssetCreate, ctx: WorkspaceContext = Depends(worker_ctx), db: Session = Depends(get_db)):
    return service.create_asset(db, ctx, data)


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)):
    return service.get_profile(db, ctx, asset_id)


@router.patch("/{asset_id}", response_model=AssetOut)
def update_asset(
    asset_id: uuid.UUID, data: AssetUpdate, ctx: WorkspaceContext = Depends(manager_ctx), db: Session = Depends(get_db)
):
    return service.update_asset(db, ctx, asset_id, data)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_asset(asset_id: uuid.UUID, ctx: WorkspaceContext = Depends(manager_ctx), db: Session = Depends(get_db)):
    service.archive_asset(db, ctx, asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{asset_id}/timeline", response_model=list[TimelineEvent])
def timeline(asset_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)):
    return service.timeline(db, ctx, asset_id)
