from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, manager_ctx, viewer_ctx, worker_ctx
from app.core.pagination import Page, PageParams, page_params

from . import lifecycle_service, service
from .models import AssetKind, HealthBand
from .schemas import (
    AssetCreate,
    AssetLifecycleOut,
    AssetOut,
    AssetUpdate,
    LifecycleRecord,
    LifecycleTemplateOut,
    TimelineEvent,
)

router = APIRouter(prefix="/workspaces/{ws}/assets", tags=["assets"])
template_router = APIRouter(prefix="/workspaces/{ws}/lifecycle-template", tags=["assets"])


@template_router.get("", response_model=LifecycleTemplateOut)
def lifecycle_template(ctx: WorkspaceContext = Depends(viewer_ctx)):
    """The stages of this workspace's operating mode and the exits per tracking mode, with the rules."""
    return lifecycle_service.template(ctx)


@router.get("", response_model=Page[AssetOut])
def list_assets(
    kind: AssetKind | None = None,
    location_id: uuid.UUID | None = None,
    health_band: HealthBand | None = None,
    q: str | None = None,
    has_open_issue: bool | None = None,
    stage: str | None = None,
    active: bool | None = None,
    page: PageParams = Depends(page_params),
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    return service.list_assets(
        db,
        ctx,
        page,
        kind=kind,
        location_id=location_id,
        health_band=health_band,
        q=q,
        has_open_issue=has_open_issue,
        stage=stage,
        active=active,
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


@router.get("/{asset_id}/lifecycle", response_model=AssetLifecycleOut)
def get_lifecycle(asset_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)):
    return lifecycle_service.view(db, ctx, service.get_asset(db, ctx, asset_id))


@router.post("/{asset_id}/lifecycle", response_model=AssetLifecycleOut, status_code=status.HTTP_201_CREATED)
def record_lifecycle(
    asset_id: uuid.UUID,
    data: LifecycleRecord,
    ctx: WorkspaceContext = Depends(worker_ctx),
    db: Session = Depends(get_db),
):
    """Record a stage change. Append-only: a mistake is corrected by a new entry (manager, with a reason)."""
    return lifecycle_service.record(db, ctx, service.get_asset(db, ctx, asset_id), data)
