from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import Attachment, SmallDict, StrictModel
from app.modules.intelligence.schemas import RecommendationOut

from .models import ObservationKind, ObservationSource


class ObservationCreate(StrictModel):
    asset_id: uuid.UUID
    observed_at: datetime | None = None  # defaults to now; may be back-dated (field notes entered later)
    kind: ObservationKind = ObservationKind.HEALTH
    health_score: float | None = Field(default=None, ge=0, le=100)
    symptoms: list[str] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(default=None, max_length=5000)
    data: SmallDict = Field(default_factory=dict)
    attachments: list[Attachment] = Field(default_factory=list, max_length=10)
    supersedes_id: uuid.UUID | None = None


class ObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID | None
    observed_at: datetime
    observer_id: uuid.UUID | None
    kind: ObservationKind
    source: ObservationSource
    health_score: float | None
    symptoms: list[str]
    notes: str | None
    data: dict
    attachments: list[dict]
    supersedes_id: uuid.UUID | None
    created_at: datetime


class ObservationCreated(BaseModel):
    observation: ObservationOut
    # Rule-based checks run immediately after the observation is stored; each is a suggestion a person can accept.
    recommendations: list[RecommendationOut]
