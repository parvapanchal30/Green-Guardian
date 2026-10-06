from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, IdMixin, JsonType, TimestampMixin
from app.core.timeutil import utcnow


class WorkspaceMode(StrEnum):
    GREEN = "green_management"
    AGRI = "agricultural_production"


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    WORKER = "worker"
    VIEWER = "viewer"


ROLE_RANK = {Role.VIEWER: 0, Role.WORKER: 1, Role.MANAGER: 2, Role.ADMIN: 3, Role.OWNER: 4}


def _in(values) -> str:
    return ", ".join(f"'{v.value}'" for v in values)


class Workspace(IdMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"
    __table_args__ = (CheckConstraint(f"mode IN ({_in(WorkspaceMode)})", name="mode"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    settings: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    # Overrides only; the effective capability set is computed from code (see capabilities.py).
    capabilities: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    # Human-readable key counters (GG-001, T-014 ...) are allocated here in later slices.
    key_counters: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Membership(IdMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "workspace_id", name="uq_memberships_user_workspace"),
        CheckConstraint(f"role IN ({_in(Role)})", name="role"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
