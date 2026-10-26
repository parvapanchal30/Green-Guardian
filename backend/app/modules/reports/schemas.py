from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Named(BaseModel):
    name: str
    count: int


class IssueStats(BaseModel):
    opened: int
    closed: int
    still_open: int  # open now, whenever they were opened
    opened_by_category: dict[str, int]
    opened_by_severity: dict[str, int]
    closed_by_outcome: dict[str, int]
    median_days_to_close: float | None  # issues closed in the period


class TaskStats(BaseModel):
    created: int
    completed: int
    cancelled: int
    completed_with_due_date: int
    completed_on_time: int
    on_time_pct: float | None
    overdue_now: int
    completed_by_type: dict[str, int]


class ActionStats(BaseModel):
    recorded: int  # effective records (corrections applied, withdrawals left out)
    by_kind: dict[str, int]
    top_products: list[Named]


class ObservationStats(BaseModel):
    recorded: int
    with_health_score: int
    with_measurements: int
    assets_observed: int
    observers: int
    by_kind: dict[str, int]


class AgentStats(BaseModel):
    suggested: int
    accepted: int
    dismissed: int
    expired: int
    open_now: int
    outcomes: dict[str, int]


class AnalyticsReport(BaseModel):
    """What happened in a period, counted from records. Every figure is a count or a share of recorded events."""

    method: Literal["statistical"] = "statistical"
    since: datetime
    until: datetime
    issues: IssueStats
    tasks: TaskStats
    actions: ActionStats
    observations: ObservationStats
    agent: AgentStats


class SpeciesSurvival(BaseModel):
    species: str
    alive: int
    dead: int
    rate: float | None


class Planting(BaseModel):
    registered: int  # individual plants registered in the period
    planted: int  # of those and others: planting date inside the period
    batches_registered: int
    plants_in_batches: int  # estimated plants in batches registered in the period
    by_species: list[Named]  # individual plants registered in the period


class Survival(BaseModel):
    alive: int
    dead: int
    rate: float | None
    by_species: list[SpeciesSurvival]


class HealthChange(BaseModel):
    assets_compared: int  # living assets with a score both before the period and at its end
    healthy_share_start: float | None
    healthy_share_end: float | None


class GrowthImpact(BaseModel):
    comparable_assets: int
    median_height_change_pct: float | None


class Canopy(BaseModel):
    trees_measured: int
    area_m2: float | None  # CALCULATED from measured canopy widths, assuming a circular crown


class Unavailable(BaseModel):
    available: Literal[False] = False
    reason: str


class ImpactReport(BaseModel):
    """Green-cover impact from records: plantings, survival, health change, measured growth, calculated canopy area.
    Nothing is estimated from outside data; what cannot be computed says why."""

    method: Literal["statistical"] = "statistical"
    since: datetime
    until: datetime
    planting: Planting
    survival: Survival
    health: HealthChange
    growth: GrowthImpact
    canopy: Canopy
    coverage: Unavailable
