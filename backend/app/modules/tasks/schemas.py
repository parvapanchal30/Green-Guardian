from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.schemas import Attachment, StrictModel
from app.modules.actions.schemas import ActionDone

from .models import Priority, TaskSource, TaskStatus, TaskType


class TaskCreate(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    type: TaskType = TaskType.OTHER
    description: str | None = Field(default=None, max_length=5000)
    issue_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None  # inferred from the issue when omitted
    location_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    priority: Priority = Priority.P3
    due_at: datetime | None = None


class TaskUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    assignee_id: uuid.UUID | None = None
    priority: Priority | None = None
    due_at: datetime | None = None


class FollowUpObservation(StrictModel):
    """Optional check recorded when a task is completed: this is how acting on an issue updates the asset's state."""

    health_score: float | None = Field(default=None, ge=0, le=100)
    symptoms: list[str] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(default=None, max_length=5000)
    attachments: list[Attachment] = Field(default_factory=list, max_length=10)


class TaskTransition(StrictModel):
    to_status: TaskStatus
    note: str | None = Field(default=None, max_length=2000)
    observation: FollowUpObservation | None = None
    action: ActionDone | None = None  # what was done, recorded as an action on the task's asset (and issue)


class TaskHistoryOut(BaseModel):
    from_status: str | None
    to_status: str
    actor_id: uuid.UUID | None
    note: str | None
    at: datetime


class TaskOut(BaseModel):
    id: uuid.UUID
    key: str
    type: TaskType
    title: str
    description: str | None
    issue_id: uuid.UUID | None
    issue_key: str | None
    asset_id: uuid.UUID | None
    asset_label: str | None
    location_id: uuid.UUID | None
    assignee_id: uuid.UUID | None
    priority: Priority
    status: TaskStatus
    source: TaskSource
    recommendation_id: uuid.UUID | None = None  # the agent recommendation this task came from, if any
    due_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    completion_notes: str | None
    overdue: bool
    created_at: datetime
    updated_at: datetime
    version: int


class TaskDetail(TaskOut):
    history: list[TaskHistoryOut]
    allowed_transitions: list[str]
