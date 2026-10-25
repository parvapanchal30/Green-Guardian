from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Metric = Literal["height_cm", "girth_cm", "canopy_m"]


class BandCounts(BaseModel):
    healthy: int
    at_risk: int
    critical: int
    no_data: int


class HealthWeek(BaseModel):
    week_start: datetime  # Monday 00:00 UTC
    observations: int  # observations with a health score that week
    assets: int  # distinct assets scored
    mean_score: float | None
    healthy: int  # scored observations by band (the band of each score, by the default thresholds)
    at_risk: int
    critical: int


class AssetChange(BaseModel):
    asset_id: uuid.UUID
    label: str
    first_score: float
    first_at: datetime
    latest_score: float
    latest_at: datetime
    change: float


class Unobserved(BaseModel):
    asset_id: uuid.UUID
    label: str
    last_observed_at: datetime | None  # None: never observed


class HealthMonitor(BaseModel):
    """Descriptive statistics over RECORDED health scores: nothing here is estimated or predicted."""

    method: Literal["statistical"] = "statistical"
    weeks: int
    now: BandCounts  # living assets by their current band
    weekly: list[HealthWeek]  # oldest first, one entry per week (empty weeks included)
    declining: list[AssetChange]  # largest drop first, at most 10
    not_observed_days: int
    not_observed_count: int
    not_observed: list[Unobserved]  # longest unobserved first, at most 10


class Measurement(BaseModel):
    observation_id: uuid.UUID
    observed_at: datetime
    height_cm: float | None
    girth_cm: float | None
    canopy_m: float | None


class AssetGrowth(BaseModel):
    asset_id: uuid.UUID
    measurements: list[Measurement]  # oldest first


class GrowthRow(BaseModel):
    asset_id: uuid.UUID
    label: str
    kind: str
    measurements: int
    first: float
    first_at: datetime
    latest: float
    latest_at: datetime
    change: float | None  # None until two measurements at least MIN_SPAN_DAYS apart
    change_pct: float | None
    per_year: float | None  # change scaled to 365 days


class GrowthMonitor(BaseModel):
    """Changes between RECORDED measurements; never an estimate of growth that was not measured."""

    method: Literal["statistical"] = "statistical"
    metric: Metric
    months: int
    min_span_days: int
    assets: list[GrowthRow]  # assets with at least one measurement of the metric in the period
    measured_assets: int
    comparable_assets: int  # with two measurements at least min_span_days apart
    median_change_pct: float | None
