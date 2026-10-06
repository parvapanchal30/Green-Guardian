from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, current_user, require_role, workspace_ctx
from app.modules.identity.models import User

from . import service
from .capabilities import effective_capabilities
from .models import Role
from .schemas import (
    CapabilityOut,
    MemberAdd,
    MemberOut,
    MemberRoleUpdate,
    WorkspaceCreate,
    WorkspaceOut,
    WorkspaceUpdate,
    WorkspaceWithRole,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])
_admin = require_role(Role.ADMIN)


def _with_role(ws, role) -> WorkspaceWithRole:
    return WorkspaceWithRole(**WorkspaceOut.model_validate(ws).model_dump(), role=role)


@router.get("", response_model=list[WorkspaceWithRole])
def list_my_workspaces(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_with_role(w, r) for w, r in service.list_workspaces(db, user)]


@router.post("", response_model=WorkspaceWithRole, status_code=status.HTTP_201_CREATED)
def create_workspace(data: WorkspaceCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ws, role = service.create_workspace(db, user, data)
    return _with_role(ws, role)


@router.get("/{ws}", response_model=WorkspaceWithRole)
def get_workspace(ctx: WorkspaceContext = Depends(workspace_ctx)):
    return _with_role(ctx.workspace, ctx.role)


@router.patch("/{ws}", response_model=WorkspaceWithRole)
def update_workspace(data: WorkspaceUpdate, ctx: WorkspaceContext = Depends(_admin), db: Session = Depends(get_db)):
    return _with_role(service.update_workspace(db, ctx, data), ctx.role)


@router.get("/{ws}/capabilities", response_model=list[CapabilityOut])
def capabilities(ctx: WorkspaceContext = Depends(workspace_ctx)):
    return [CapabilityOut(**c.__dict__) for c in effective_capabilities(ctx.workspace.capabilities)]


@router.get("/{ws}/members", response_model=list[MemberOut])
def list_members(ctx: WorkspaceContext = Depends(workspace_ctx), db: Session = Depends(get_db)):
    return service.list_members(db, ctx)


@router.post("/{ws}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def add_member(data: MemberAdd, ctx: WorkspaceContext = Depends(_admin), db: Session = Depends(get_db)):
    return service.add_member(db, ctx, data.email, data.role)


@router.patch("/{ws}/members/{user_id}", response_model=MemberOut)
def change_member_role(
    user_id: uuid.UUID,
    data: MemberRoleUpdate,
    ctx: WorkspaceContext = Depends(_admin),
    db: Session = Depends(get_db),
):
    return service.change_member_role(db, ctx, user_id, data.role)


@router.delete("/{ws}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(user_id: uuid.UUID, ctx: WorkspaceContext = Depends(_admin), db: Session = Depends(get_db)):
    service.remove_member(db, ctx, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
