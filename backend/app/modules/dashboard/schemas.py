from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class Filters(BaseModel):
    location_id: uuid.UUID | None = None
    kind: str | None = None


class HealthCounts(BaseModel):
    healthy: int
    at_risk: int
    critical: int
    unknown: int  # no health score recorded yet: reported, never counted as healthy


class AssetMetrics(BaseModel):
    total: int  # ACTIVE assets: not archived and not exited
    by_kind: dict[str, int]
    exited: int = 0  # assets that left the lifecycle (dead, failed, removed, replaced); not in any other figure
    health: HealthCounts


class WorkMetrics(BaseModel):
    open_issues: int
    open_issues_by_severity: dict[str, int]
    open_tasks: int
    overdue_tasks: int
    tasks_due_next_7_days: int
    # assets with no observation within the workspace's inspection interval (the same threshold the agent uses)
    inspections_due: int
    inspection_interval_days: int
    open_recommendations: int


class Kpi(BaseModel):
    """A mode-specific headline figure. Either computed from recorded data (with its basis) or explicitly unavailable
    with the reason: a number that cannot be computed is never shown."""

    key: str
    label: str
    available: bool
    value: float | None = None
    unit: str | None = None
    basis: str | None = None
    reason: str | None = None


class Activity(BaseModel):
    at: datetime
    type: str  # observation | issue | task
    ref_id: uuid.UUID
    asset_id: uuid.UUID | None
    key: str | None
    title: str
    detail: str | None


class Dashboard(BaseModel):
    mode: str
    as_of: datetime
    filters: Filters
    assets: AssetMetrics
    work: WorkMetrics
    kpis: list[Kpi]
    recent_activity: list[Activity]
