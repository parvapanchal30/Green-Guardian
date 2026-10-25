from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, IdMixin, UtcDateTime
from app.core.timeutil import utcnow

TASK_TYPES = ("inspect", "monitor")
OUTCOMES = ("created", "skipped_open_task", "skipped_inactive_asset")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class InspectionSchedule(IdMixin, Base):
    """A recurring inspection (ADR-062): every `interval_days` a task is created for one asset or one location.

    This is CONFIGURATION, so it is editable (every change is audited); what it produced is the append-only
    `schedule_occurrences` table. A schedule is paused, never deleted, so its history keeps its meaning."""

    __tablename__ = "inspection_schedules"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_inspection_schedules_workspace_id_id"),
        ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["biological_assets.workspace_id", "biological_assets.id"],
            name="fk_inspection_schedules_asset",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "location_id"],
            ["locations.workspace_id", "locations.id"],
            name="fk_inspection_schedules_location",
            ondelete="CASCADE",
        ),
        CheckConstraint("(asset_id IS NULL) <> (location_id IS NULL)", name="one_subject"),
        CheckConstraint(f"task_type IN ({_in(TASK_TYPES)})", name="task_type"),
        CheckConstraint("interval_days BETWEEN 1 AND 365", name="interval_days"),
        CheckConstraint("lead_days BETWEEN 0 AND 30 AND lead_days < interval_days", name="lead_days"),
        CheckConstraint("priority IN ('p1', 'p2', 'p3', 'p4')", name="priority"),
        Index("ix_inspection_schedules_due", "active", "next_due_at"),
        Index("ix_inspection_schedules_asset", "workspace_id", "asset_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    location_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    task_type: Mapped[str] = mapped_column(String(16), default="inspect", nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    lead_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_due_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    priority: Mapped[str] = mapped_column(String(2), default="p3", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ScheduleOccurrence(IdMixin, Base):
    """APPEND-ONLY: one row per due date a schedule reached, saying what happened (a task was created, or why not).
    The unique (schedule, due date) key makes generation idempotent: two workers can never create the same task."""

    __tablename__ = "schedule_occurrences"
    __table_args__ = (
        UniqueConstraint("workspace_id", "schedule_id", "due_at", name="uq_schedule_occurrences_due"),
        ForeignKeyConstraint(
            ["workspace_id", "schedule_id"],
            ["inspection_schedules.workspace_id", "inspection_schedules.id"],
            name="fk_schedule_occurrences_schedule",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "task_id"],
            ["tasks.workspace_id", "tasks.id"],
            name="fk_schedule_occurrences_task",
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"outcome IN ({_in(OUTCOMES)})", name="outcome"),
        CheckConstraint("(outcome = 'created') = (task_id IS NOT NULL)", name="task_when_created"),
        CheckConstraint("missed >= 0", name="missed"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    schedule_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    due_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # earlier due dates passed over because nothing generated them in time (the worker was not running)
    missed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, nullable=False)
