from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, manager_ctx, viewer_ctx
from app.core.pagination import Page, PageParams, page_params

from . import service
from .schemas import ProtocolCreate, ProtocolDetail, ProtocolSummary, SignoffCreate

router = APIRouter(prefix="/workspaces/{ws}/evaluation-protocols", tags=["evaluation-protocols"])


@router.get("/template")
def template(ctx: WorkspaceContext = Depends(viewer_ctx)) -> dict[str, Any]:
    """The proposed plant-disease protocol (P-DIS-1). A starting point, not an approved protocol."""
    return service.template()


@router.get("", response_model=Page[ProtocolSummary])
def list_protocols(
    page: PageParams = Depends(page_params), ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)
):
    return service.list_protocols(db, ctx, page)


@router.post("", response_model=ProtocolDetail, status_code=201)
def create(data: ProtocolCreate, ctx: WorkspaceContext = Depends(manager_ctx), db: Session = Depends(get_db)):
    """Register a protocol version. Content is validated: every threshold needs a stated basis, and thresholds that need
    domain expertise must be pending and carry no invented value."""
    return service.create(db, ctx, data)


@router.get("/{protocol_id}", response_model=ProtocolDetail)
def get_protocol(protocol_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)):
    return service.get_detail(db, ctx, protocol_id)


@router.post("/{protocol_id}/signoffs", response_model=ProtocolDetail, status_code=201)
def sign(
    protocol_id: uuid.UUID,
    data: SignoffCreate,
    ctx: WorkspaceContext = Depends(manager_ctx),
    db: Session = Depends(get_db),
):
    """Record a sign-off in one required role. The signer is the signed-in user; their qualification is stored as declared
    and always unverified, so a protocol cannot become approved until verification exists."""
    return service.sign(db, ctx, protocol_id, data)
