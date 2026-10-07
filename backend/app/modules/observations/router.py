from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, viewer_ctx, worker_ctx
from app.core.pagination import Page, PageParams, page_params

from . import service
from .schemas import ObservationCreate, ObservationCreated, ObservationOut

router = APIRouter(prefix="/workspaces/{ws}/observations", tags=["observations"])


@router.post("", response_model=ObservationCreated, status_code=status.HTTP_201_CREATED)
def create_observation(
    data: ObservationCreate, ctx: WorkspaceContext = Depends(worker_ctx), db: Session = Depends(get_db)
):
    """Observations are immutable. To correct one, post a new observation with `supersedes_id`."""
    return service.create_observation(db, ctx, data)


@router.get("", response_model=Page[ObservationOut])
def list_observations(
    asset_id: uuid.UUID | None = None,
    page: PageParams = Depends(page_params),
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    return service.list_observations(db, ctx, page, asset_id=asset_id)


@router.get("/{observation_id}", response_model=ObservationOut)
def get_observation(
    observation_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)
):
    return ObservationOut.model_validate(service.get_observation(db, ctx, observation_id))
