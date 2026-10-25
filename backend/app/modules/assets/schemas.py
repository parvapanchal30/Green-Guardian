from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import SmallDict, StrictModel

from .models import AssetKind, HealthBand, TrackingMode


class AssetCreate(StrictModel):
    label: str = Field(min_length=1, max_length=200)
    kind: AssetKind
    tracking_mode: TrackingMode = TrackingMode.INDIVIDUAL
    species_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    tag_code: str | None = Field(default=None, min_length=1, max_length=100)
    estimated_count: int | None = Field(default=None, gt=0, le=100_000_000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    planted_at: date | None = None
    # Initial lifecycle stage (default "planted"); must belong to the workspace's lifecycle template and not be an exit.
    stage: str | None = Field(default=None, min_length=1, max_length=32)
    attributes: SmallDict = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _consistent(self) -> AssetCreate:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be given together")
        if self.tracking_mode == TrackingMode.POPULATION and self.estimated_count is None:
            raise ValueError("a population asset (e.g. a crop batch) needs estimated_count")
        if self.tracking_mode == TrackingMode.INDIVIDUAL and self.estimated_count is not None:
            raise ValueError("estimated_count only applies to population assets")
        return self


class AssetUpdate(StrictModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    species_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    tag_code: str | None = Field(default=None, min_length=1, max_length=100)
    estimated_count: int | None = Field(default=None, gt=0, le=100_000_000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    attributes: SmallDict | None = None
    notes: str | None = Field(default=None, max_length=5000)


class StateOut(BaseModel):
    health_score: float | None
    health_band: HealthBand | None
    health_observed_at: datetime | None
    last_observed_at: datetime | None
    open_issue_count: int
    open_task_count: int
    last_resolved_at: datetime | None


class AssetOut(BaseModel):
    id: uuid.UUID
    label: str
    kind: AssetKind
    tracking_mode: TrackingMode
    tag_code: str | None
    estimated_count: int | None
    current_stage: str
    is_active: bool  # False once the asset has left the lifecycle (dead, failed, removed, replaced)
    species_id: uuid.UUID | None
    species_name: str | None
    location_id: uuid.UUID | None
    location_name: str | None
    latitude: float | None
    longitude: float | None
    planted_at: date | None
    attributes: dict
    notes: str | None
    created_at: datetime
    archived_at: datetime | None
    state: StateOut


class LifecycleRecord(StrictModel):
    stage: str = Field(min_length=1, max_length=32)
    entered_at: datetime | None = None  # when the asset entered the stage; default now. Never in the future.
    note: str | None = Field(default=None, max_length=1000)
    correction: bool = False  # moving back, or reinstating an exited asset: needs a manager and a written reason


class LifecycleEventOut(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    stage: str
    stage_label: str
    previous_stage: str | None
    entered_at: datetime
    recorded_at: datetime
    source: str
    correction: bool
    note: str | None
    actor_id: uuid.UUID | None


class StageChoice(BaseModel):
    key: str
    label: str
    kind: str  # stage | exit
    manager_only: bool = False


class LifecycleTemplateOut(BaseModel):
    mode: str
    stages: list[StageChoice]
    exits_individual: list[StageChoice]
    exits_population: list[StageChoice]
    rules: list[str]


class AssetLifecycleOut(BaseModel):
    """Everything the asset page needs: where the asset is, what can be recorded next, and the history."""

    asset_id: uuid.UUID
    current_stage: str
    is_active: bool
    next_choices: list[StageChoice]
    history: list[LifecycleEventOut]


class TimelineEvent(BaseModel):
    at: datetime
    type: str  # observation | issue | task | lifecycle | harvest | action
    ref_id: uuid.UUID
    key: str | None
    title: str
    detail: str | None
    actor_id: uuid.UUID | None
