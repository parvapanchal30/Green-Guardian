from __future__ import annotations

import re
import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import Conflict, Forbidden, NotFound
from app.modules.identity.models import Organization, User
from app.modules.identity.service import get_user_by_email

from .models import ROLE_RANK, Membership, Role, Workspace
from .schemas import MemberOut, WorkspaceCreate, WorkspaceUpdate


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "org"
    return f"{base}-{secrets.token_hex(3)}"


def create_workspace(db: Session, user: User, data: WorkspaceCreate) -> tuple[Workspace, Role]:
    org = Organization(name=data.name.strip(), slug=_slug(data.name))
    db.add(org)
    db.flush()
    ws = Workspace(
        organization_id=org.id,
        name=data.name.strip(),
        mode=data.mode.value,
        timezone=data.timezone,
        settings={},
        capabilities={},
        key_counters={"issue": 0, "task": 0},
    )
    db.add(ws)
    db.flush()
    db.add(Membership(workspace_id=ws.id, user_id=user.id, role=Role.OWNER.value))
    db.commit()
    return ws, Role.OWNER


def list_workspaces(db: Session, user: User) -> list[tuple[Workspace, Role]]:
    rows = db.execute(
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user.id, Workspace.archived_at.is_(None))
        .order_by(Workspace.created_at)
    ).all()
    return [(w, Role(r)) for w, r in rows]


def update_workspace(db: Session, ctx: WorkspaceContext, data: WorkspaceUpdate) -> Workspace:
    ws = ctx.workspace
    if data.name is not None:
        ws.name = data.name.strip()
    if data.timezone is not None:
        ws.timezone = data.timezone
    if data.settings is not None:
        ws.settings = data.settings
    db.commit()
    return ws


# ---- members (every query is filtered by ctx.workspace_id) ----


def list_members(db: Session, ctx: WorkspaceContext) -> list[MemberOut]:
    rows = db.execute(
        select(User, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.workspace_id == ctx.workspace_id)
        .order_by(User.name)
    ).all()
    return [MemberOut(user_id=u.id, email=u.email, name=u.name, role=Role(r)) for u, r in rows]


def _membership(db: Session, ctx: WorkspaceContext, user_id: uuid.UUID) -> Membership:
    m = db.scalar(select(Membership).where(Membership.workspace_id == ctx.workspace_id, Membership.user_id == user_id))
    if m is None:
        raise NotFound("Member not found", code="member_not_found")
    return m


def _owner_count(db: Session, ctx: WorkspaceContext) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.workspace_id == ctx.workspace_id, Membership.role == Role.OWNER.value)
        )
        or 0
    )


def _guard_role_change(ctx: WorkspaceContext, target_role: Role, new_role: Role | None) -> None:
    """Only owners may grant, change or remove the owner role; nobody may touch a higher role than their own."""
    touched = [target_role] + ([new_role] if new_role else [])
    if Role.OWNER in touched and ctx.role != Role.OWNER:
        raise Forbidden("Only an owner can grant or change the owner role", code="owner_only")
    if ROLE_RANK[target_role] > ROLE_RANK[ctx.role]:
        raise Forbidden("Cannot modify a member with a higher role", code="insufficient_role")


def add_member(db: Session, ctx: WorkspaceContext, email: str, role: Role) -> MemberOut:
    _guard_role_change(ctx, role, None)
    user = get_user_by_email(db, email)
    exists = db.scalar(
        select(Membership.id).where(Membership.workspace_id == ctx.workspace_id, Membership.user_id == user.id)
    )
    if exists:
        raise Conflict("User is already a member", code="already_member")
    db.add(Membership(workspace_id=ctx.workspace_id, user_id=user.id, role=role.value))
    db.commit()
    return MemberOut(user_id=user.id, email=user.email, name=user.name, role=role)


def change_member_role(db: Session, ctx: WorkspaceContext, user_id: uuid.UUID, role: Role) -> MemberOut:
    m = _membership(db, ctx, user_id)
    current = Role(m.role)
    _guard_role_change(ctx, current, role)
    if current == Role.OWNER and role != Role.OWNER and _owner_count(db, ctx) <= 1:
        raise Conflict("A workspace must keep at least one owner", code="last_owner")
    m.role = role.value
    db.commit()
    user = db.get(User, user_id)
    assert user is not None
    return MemberOut(user_id=user.id, email=user.email, name=user.name, role=role)


def remove_member(db: Session, ctx: WorkspaceContext, user_id: uuid.UUID) -> None:
    m = _membership(db, ctx, user_id)
    current = Role(m.role)
    _guard_role_change(ctx, current, None)
    if current == Role.OWNER and _owner_count(db, ctx) <= 1:
        raise Conflict("A workspace must keep at least one owner", code="last_owner")
    db.delete(m)
    db.commit()
