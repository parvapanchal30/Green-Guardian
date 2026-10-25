from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, manager_ctx, viewer_ctx, worker_ctx
from app.modules.assets.service import get_asset

from . import service
from .schemas import ActionCorrect, ActionCreate, AssetActions

router = APIRouter(prefix="/workspaces/{ws}/assets/{asset_id}/actions", tags=["actions"])


@router.get("", response_model=AssetActions)
def list_actions(asset_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)):
    """The work done to this asset, newest first, corrections included (append-only)."""
    return service.view(db, ctx, get_asset(db, ctx, asset_id, include_archived=True))


@router.post("", response_model=AssetActions, status_code=status.HTTP_201_CREATED)
def record_action(
    asset_id: uuid.UUID, data: ActionCreate, ctx: WorkspaceContext = Depends(worker_ctx), db: Session = Depends(get_db)
):
    """Record work done; optionally for an open issue, and optionally with a follow-up inspection N days later."""
    return service.record(db, ctx, get_asset(db, ctx, asset_id), data)


@router.post("/{action_id}/correct", response_model=AssetActions, status_code=status.HTTP_201_CREATED)
def correct_action(
    asset_id: uuid.UUID,
    action_id: uuid.UUID,
    data: ActionCorrect,
    ctx: WorkspaceContext = Depends(manager_ctx),
    db: Session = Depends(get_db),
):
    """Records are never edited: a manager replaces one with a corrected record and a reason (or withdraws it)."""
    return service.correct(db, ctx, get_asset(db, ctx, asset_id), action_id, data)
