from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import StrictModel

TaskType = Literal["inspect", "monitor"]
Priority = Literal["p1", "p2", "p3", "p4"]


class _Timing(StrictModel):
    interval_days: int | None = Field(default=None, ge=1, le=365)
    lead_days: int | None = Field(default=None, ge=0, le=30)


class ScheduleCreate(_Timing):
    asset_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)  # default: "Inspect <asset or location>"
    task_type: TaskType = "inspect"
    interval_days: int = Field(ge=1, le=365)  # type: ignore[assignment]
    lead_days: int = Field(default=0, ge=0, le=30)  # type: ignore[assignment]  # create the task this many days early
    first_due_at: datetime | None = None  # default: now (the first inspection is due straight away)
    assignee_id: uuid.UUID | None = None
    priority: Priority = "p3"

    @model_validator(mode="after")
    def _one_subject_and_timing(self):
        if (self.asset_id is None) == (self.location_id is None):
            raise ValueError("give exactly one of asset_id and location_id")
        if self.lead_days >= self.interval_days:
            raise ValueError("lead_days must be smaller than interval_days")
        return self


class ScheduleUpdate(_Timing):
    """Any subset. Changing the interval does not move the next due date; send next_due_at to move it."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    next_due_at: datetime | None = None
    assignee_id: uuid.UUID | None = None
    priority: Priority | None = None
    active: bool | None = None


class OccurrenceOut(BaseModel):
    due_at: datetime
    outcome: str
    task_id: uuid.UUID | None
    task_key: str | None
    task_status: str | None
    missed: int
    created_at: datetime


class ScheduleOut(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID | None
    asset_label: str | None
    location_id: uuid.UUID | None
    location_name: str | None
    title: str
    task_type: str
    interval_days: int
    lead_days: int
    next_due_at: datetime
    assignee_id: uuid.UUID | None
    priority: str
    active: bool
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    version: int


class ScheduleDetail(ScheduleOut):
    occurrences: list[OccurrenceOut]  # newest first, at most 50


class GenerateResult(BaseModel):
    """What one pass over the due schedules did."""

    due: int
    created: int
    skipped_open_task: int
    skipped_inactive_asset: int
    task_keys: list[str]
