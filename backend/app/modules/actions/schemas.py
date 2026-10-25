from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import StrictModel

Kind = Literal["treat", "water", "fertilize", "prune", "pest_control", "weed", "mulch", "replant", "other"]
Unit = Literal["l", "ml", "kg", "g", "count"]


class _Amount(StrictModel):
    quantity: float | None = Field(default=None, gt=0, le=1_000_000, allow_inf_nan=False)
    unit: Unit | None = None

    @model_validator(mode="after")
    def _quantity_has_unit(self):
        if (self.quantity is None) != (self.unit is None):
            raise ValueError("give both a quantity and a unit, or neither")
        return self


class ActionDone(_Amount):
    """What was done, as recorded when a task is completed (the task gives the asset, issue and time)."""

    kind: Kind
    product: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=2000)


class ActionCreate(ActionDone):
    performed_at: datetime | None = None  # default now; never in the future, never before the planting date
    issue_id: uuid.UUID | None = None  # an OPEN issue of the same asset
    performed_by: uuid.UUID | None = None  # default: the person recording; a manager may name another member
    # Schedule an inspection to check the result: a task due this many days later, linked to the issue.
    follow_up_days: int | None = Field(default=None, ge=1, le=90)


class ActionCorrect(_Amount):
    """Replaces a record, keeping its asset, issue and task. `withdrawn` marks a record that should not exist."""

    kind: Kind
    product: str | None = Field(default=None, max_length=120)
    performed_at: datetime | None = None  # default: keep the original time
    withdrawn: bool = False
    note: str = Field(min_length=10, max_length=2000)  # the reason for the correction


class ActionOut(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    issue_id: uuid.UUID | None
    issue_key: str | None
    task_id: uuid.UUID | None
    task_key: str | None
    kind: str
    product: str | None
    quantity: float | None
    unit: str | None
    performed_at: datetime
    performed_by: uuid.UUID | None
    note: str | None
    follow_up_task_id: uuid.UUID | None
    follow_up_task_key: str | None
    supersedes_id: uuid.UUID | None
    superseded_by: uuid.UUID | None
    effective: bool  # False once a correction replaced it
    withdrawn: bool
    recorded_by: uuid.UUID | None
    recorded_at: datetime


class AssetActions(BaseModel):
    asset_id: uuid.UUID
    history: list[ActionOut]


VerificationStatus = Literal[
    "not_applicable", "awaiting_follow_up", "improved", "unchanged", "worse", "observed_without_score"
]


class Verification(BaseModel):
    """Did the work help? A RULE over recorded observations, never a judgement of the plant (ADR-059).

    The baseline is the latest health score recorded up to the first action on the issue (or up to its opening); the
    follow-up is the latest observation after the last action (or after the opening when nothing was recorded),
    up to the closing time for a closed issue."""

    status: VerificationStatus
    method: Literal["rule"] = "rule"
    min_change: float  # a change smaller than this, in health points, counts as unchanged
    actions: int  # effective actions on the issue
    last_action_at: datetime | None
    baseline_score: float | None
    baseline_at: datetime | None
    follow_up_score: float | None
    follow_up_at: datetime | None
    change: float | None
    required_for_success: bool  # closing as fixed or mitigated needs a follow-up observation
