from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import StrictModel
from app.modules.observations.schemas import ObservationOut
from app.modules.tasks.schemas import TaskOut

from .models import IssueCategory, IssueSource, ResolutionOutcome, Severity


class IssueCreate(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    category: IssueCategory = IssueCategory.OTHER
    severity: Severity = Severity.MEDIUM
    asset_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    observation_id: uuid.UUID | None = None  # the evidence this issue is created from
    assignee_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _has_subject(self) -> IssueCreate:
        if not (self.asset_id or self.location_id or self.observation_id):
            raise ValueError("an issue needs an asset_id, a location_id or an observation_id")
        return self


class IssueUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    severity: Severity | None = None
    assignee_id: uuid.UUID | None = None


class Resolution(StrictModel):
    outcome: ResolutionOutcome
    notes: str | None = Field(default=None, max_length=5000)
    cancel_open_tasks: bool = False  # explicit opt-in: otherwise open tasks block resolution


class IssueTransition(StrictModel):
    to_state: str = Field(min_length=1, max_length=48)
    note: str | None = Field(default=None, max_length=2000)
    resolution: Resolution | None = None


class EvidenceAdd(StrictModel):
    observation_id: uuid.UUID


class HistoryOut(BaseModel):
    from_state: str | None
    to_state: str
    actor_id: uuid.UUID | None
    note: str | None
    at: datetime


class IssueOut(BaseModel):
    id: uuid.UUID
    key: str
    title: str
    description: str | None
    category: IssueCategory
    severity: Severity
    workflow_key: str
    state: str
    is_open: bool
    asset_id: uuid.UUID | None
    asset_label: str | None
    location_id: uuid.UUID | None
    assignee_id: uuid.UUID | None
    reporter_id: uuid.UUID | None
    source: IssueSource
    origin_observation_id: uuid.UUID | None
    recommendation_id: uuid.UUID | None
    opened_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    resolution_outcome: ResolutionOutcome | None
    resolution_notes: str | None
    resolved_by: uuid.UUID | None
    version: int


class IssueDetail(IssueOut):
    history: list[HistoryOut]
    evidence: list[ObservationOut]
    tasks: list[TaskOut]
    allowed_transitions: list[str]


class WorkflowOut(BaseModel):
    key: str
    label: str
    states: list[str]
    initial: str
    terminal: list[str]
    transitions: dict[str, list[str]]
