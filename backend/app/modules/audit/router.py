from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, manager_ctx
from app.core.pagination import Page, PageParams, page_params

from . import service
from .schemas import AuditEventOut

router = APIRouter(prefix="/workspaces/{ws}/audit", tags=["audit"])


@router.get("", response_model=Page[AuditEventOut])
def list_audit_events(
    action: str | None = None,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    request_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    page: PageParams = Depends(page_params),
    ctx: WorkspaceContext = Depends(manager_ctx),
    db: Session = Depends(get_db),
):
    """The workspace's audit trail, newest first. Read-only: there is deliberately no way to create, change or delete
    an audit record through the API. `action` is a prefix (for example `issue.` or `member.`). Managers and owners
    only."""
    return service.list_events(
        db,
        ctx,
        page,
        action=action,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        request_id=request_id,
        since=since,
        until=until,
    )
