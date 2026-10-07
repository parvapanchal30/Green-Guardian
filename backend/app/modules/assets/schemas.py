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


class TimelineEvent(BaseModel):
    at: datetime
    type: str  # observation | issue | task
    ref_id: uuid.UUID
    key: str | None
    title: str
    detail: str | None
    actor_id: uuid.UUID | None
