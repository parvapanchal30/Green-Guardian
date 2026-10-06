"""Request dependencies: authentication and the single workspace-scoping path.

Every tenant resource handler must depend on `workspace_ctx` (or `require_role(...)`); repositories
and services take the resulting WorkspaceContext and filter by `ctx.workspace_id`. There is no
unscoped query helper for tenant tables.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.errors import Forbidden, NotFound, Unauthorized
from app.core.security import decode_access_token
from app.modules.identity.models import User
from app.modules.identity.service import get_user
from app.modules.workspaces.models import ROLE_RANK, Membership, Role, Workspace

_bearer = HTTPBearer(auto_error=False)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise Unauthorized("Missing bearer token", code="missing_token")
    return get_user(db, decode_access_token(creds.credentials, settings))


@dataclass(frozen=True)
class WorkspaceContext:
    workspace: Workspace
    user: User
    role: Role

    @property
    def workspace_id(self) -> uuid.UUID:
        return self.workspace.id

    def has_role(self, minimum: Role) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[minimum]


def workspace_ctx(
    ws: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> WorkspaceContext:
    """Resolve {ws} for the caller. Non-members get 404 (existence is not revealed)."""
    row = db.execute(
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Workspace.id == ws, Membership.user_id == user.id, Workspace.archived_at.is_(None))
    ).first()
    if row is None:
        raise NotFound("Workspace not found", code="workspace_not_found")
    workspace, role = row
    return WorkspaceContext(workspace=workspace, user=user, role=Role(role))


def require_role(minimum: Role) -> Callable[..., WorkspaceContext]:
    def _dep(ctx: WorkspaceContext = Depends(workspace_ctx)) -> WorkspaceContext:
        if not ctx.has_role(minimum):
            raise Forbidden(f"Requires role '{minimum.value}' or higher", code="insufficient_role")
        return ctx

    return _dep
