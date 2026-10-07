from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import Unprocessable

from .models import Membership


def ensure_member(db: Session, ctx: WorkspaceContext, user_id: uuid.UUID | None) -> None:
    """An assignee must belong to the same workspace (otherwise work could leak to an outsider)."""
    if user_id is None:
        return
    ok = db.scalar(
        select(Membership.id).where(Membership.workspace_id == ctx.workspace_id, Membership.user_id == user_id)
    )
    if ok is None:
        raise Unprocessable("assignee_id must be a member of this workspace", code="assignee_not_member")
