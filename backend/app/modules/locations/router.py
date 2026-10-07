from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, manager_ctx, viewer_ctx
from app.core.pagination import Page, PageParams, page_params

from . import service
from .models import LocationKind
from .service import LocationCreate, LocationOut

router = APIRouter(prefix="/workspaces/{ws}/locations", tags=["locations"])


@router.get("", response_model=Page[LocationOut])
def list_locations(
    kind: LocationKind | None = None,
    page: PageParams = Depends(page_params),
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    return service.list_locations(db, ctx, page, kind)


@router.post("", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def create_location(data: LocationCreate, ctx: WorkspaceContext = Depends(manager_ctx), db: Session = Depends(get_db)):
    return service.create_location(db, ctx, data)


@router.get("/{location_id}", response_model=LocationOut)
def get_location(location_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)):
    return service.get_location(db, ctx, location_id)
