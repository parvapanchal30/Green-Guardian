from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, manager_ctx, viewer_ctx

from . import service
from .schemas import GenerateResult, ScheduleCreate, ScheduleDetail, ScheduleOut, ScheduleUpdate

router = APIRouter(prefix="/workspaces/{ws}/schedules", tags=["schedules"])


@router.get("", response_model=list[ScheduleOut])
def list_schedules(
    asset_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    active: bool | None = None,
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    return service.list_schedules(db, ctx, asset_id=asset_id, location_id=location_id, active=active)


@router.post("", response_model=ScheduleDetail, status_code=status.HTTP_201_CREATED)
def create_schedule(data: ScheduleCreate, ctx: WorkspaceContext = Depends(manager_ctx), db: Session = Depends(get_db)):
    """A recurring inspection for one asset or one location. A first one that is already due gets its task now."""
    return service.create(db, ctx, data)


@router.post("/generate", response_model=GenerateResult)
def generate_due(ctx: WorkspaceContext = Depends(manager_ctx), db: Session = Depends(get_db)):
    """Create the tasks of this workspace's due schedules now (the worker also does this on its own)."""
    return service.generate(db, workspace_id=ctx.workspace_id)


@router.get("/{schedule_id}", response_model=ScheduleDetail)
def get_schedule(schedule_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)):
    return service.get_detail(db, ctx, schedule_id)


@router.patch("/{schedule_id}", response_model=ScheduleDetail)
def update_schedule(
    schedule_id: uuid.UUID,
    data: ScheduleUpdate,
    ctx: WorkspaceContext = Depends(manager_ctx),
    db: Session = Depends(get_db),
):
    """Edit, pause (active=false) or resume. Schedules are never deleted, so their history stays meaningful."""
    return service.update(db, ctx, schedule_id, data)
