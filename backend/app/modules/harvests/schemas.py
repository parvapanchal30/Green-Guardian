from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.schemas import StrictModel

Unit = Literal["kg", "t", "count", "l"]


class HarvestCreate(StrictModel):
    quantity: float = Field(gt=0, le=1_000_000_000, allow_inf_nan=False)
    unit: Unit
    harvested_at: datetime | None = None  # default now; never in the future, never before the planting date
    grade: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=1000)


class HarvestCorrect(StrictModel):
    """Replaces a record. Quantity 0 withdraws it. A reason is required."""

    quantity: float = Field(ge=0, le=1_000_000_000, allow_inf_nan=False)
    unit: Unit
    harvested_at: datetime | None = None  # default: keep the original date
    grade: str | None = Field(default=None, max_length=40)
    note: str = Field(min_length=10, max_length=1000)


class HarvestOut(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    harvested_at: datetime
    quantity: float
    unit: str
    grade: str | None
    note: str | None
    supersedes_id: uuid.UUID | None
    superseded_by: uuid.UUID | None
    effective: bool  # False once a correction replaced it
    withdrawn: bool  # an effective correction with quantity 0
    recorded_by: uuid.UUID | None
    recorded_at: datetime


class HarvestTotals(BaseModel):
    """Totals per unit over the EFFECTIVE records. Units are never converted into each other except kg and t (mass)."""

    by_unit: dict[str, float]
    mass_tonnes: float
    records: int


class PeriodTotals(BaseModel):
    by_unit: dict[str, float]
    mass_tonnes: float
    records: int


class MonthTotals(PeriodTotals):
    month: str  # YYYY-MM (UTC)


class AssetTotals(PeriodTotals):
    asset_id: uuid.UUID
    asset_label: str


class HarvestRow(HarvestOut):
    asset_label: str


class HarvestOverview(BaseModel):
    """Every EFFECTIVE harvest of the workspace in a period (corrections applied, withdrawn records left out).
    Units are never converted into each other except kg and t (mass)."""

    since: datetime
    until: datetime
    totals: HarvestTotals
    by_month: list[MonthTotals]
    by_asset: list[AssetTotals]
    records: list[HarvestRow]  # newest first
    truncated: bool  # more records than listed (the totals still cover all of them)


class AssetHarvests(BaseModel):
    asset_id: uuid.UUID
    totals: HarvestTotals
    history: list[HarvestOut]
