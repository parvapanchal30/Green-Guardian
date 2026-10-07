from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import StrictModel

from .models import Method, RecommendationStatus


class RecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rule_key: str
    method: Method
    asset_id: uuid.UUID
    title: str
    explanation: str
    evidence: dict
    proposed_action: dict
    severity: str
    status: RecommendationStatus
    accepted_entity_type: str | None
    accepted_entity_id: uuid.UUID | None
    dismissed_reason: str | None
    created_at: datetime
    decided_at: datetime | None


class AcceptRecommendation(StrictModel):
    """Optional overrides when a person accepts a recommendation (the proposal is only a default)."""

    assignee_id: uuid.UUID | None = None
    due_at: datetime | None = None
    severity: str | None = Field(default=None, pattern="^(low|medium|high|critical)$")


class DismissRecommendation(StrictModel):
    reason: str = Field(min_length=3, max_length=1000)


class RuleInfo(BaseModel):
    key: str
    method: str
    description: str
    parameters: dict


class AgentRunOut(BaseModel):
    evaluated_assets: int
    created: list[RecommendationOut]
    rules: list[RuleInfo]
    note: str = "Rule-based checks on recorded data. No machine-learning or language-model output is produced."
