from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, IdMixin, UtcDateTime
from app.core.timeutil import utcnow


class TaskType(StrEnum):
    WATER = "water"
    FERTILIZE = "fertilize"
    INSPECT = "inspect"
    TREAT = "treat"
    PRUNE = "prune"
    PLANT = "plant"
    REPLACE = "replace"
    HARVEST = "harvest"
    MONITOR = "monitor"
    OTHER = "other"


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


OPEN_TASK_STATUSES = (TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED)


class Priority(StrEnum):
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"
    P4 = "p4"


class TaskSource(StrEnum):
    MANUAL = "manual"
    ISSUE = "issue"
    AGENT = "agent"
    SCHEDULE = "schedule"


def _in(values) -> str:
    return ", ".join(f"'{v.value}'" for v in values)


class Task(IdMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_tasks_workspace_id_id"),
        UniqueConstraint("workspace_id", "key", name="uq_tasks_workspace_key"),
        ForeignKeyConstraint(
            ["workspace_id", "issue_id"],
            ["issues.workspace_id", "issues.id"],
            name="fk_tasks_issue",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["biological_assets.workspace_id", "biological_assets.id"],
            name="fk_tasks_asset",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "location_id"],
            ["locations.workspace_id", "locations.id"],
            name="fk_tasks_location",
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"type IN ({_in(TaskType)})", name="type"),
        CheckConstraint(f"status IN ({_in(TaskStatus)})", name="status"),
        CheckConstraint(f"priority IN ({_in(Priority)})", name="priority"),
        CheckConstraint(f"source IN ({_in(TaskSource)})", name="source"),
        Index("ix_tasks_workspace_assignee_status_due", "workspace_id", "assignee_id", "status", "due_at"),
        Index("ix_tasks_workspace_issue", "workspace_id", "issue_id"),
        Index("ix_tasks_workspace_asset", "workspace_id", "asset_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(32), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    issue_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    location_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    priority: Mapped[str] = mapped_column(String(2), default=Priority.P3.value, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.TODO.value, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default=TaskSource.MANUAL.value, nullable=False)
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL"), index=True
    )
    due_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    completion_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class TaskStatusHistory(IdMixin, Base):
    """APPEND-ONLY audit of every status change (a trigger rejects UPDATE/DELETE)."""

    __tablename__ = "task_status_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["tasks.workspace_id", "tasks.id"],
            name="fk_task_status_history_task",
            ondelete="CASCADE",
        ),
        Index("ix_task_status_history_task_at", "task_id", "at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    note: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, nullable=False)
