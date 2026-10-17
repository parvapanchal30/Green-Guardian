"""Rule interface for the Botanical Operations Agent (method = RULE).

Pure functions over plain data: no DB, no I/O. Rules never write; they return Findings
that a service later persists as deduplicated Recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.modules.intelligence.ports import WeatherContext

# Version of each rule's logic. Bump it when a rule's behaviour changes, so every recommendation and run says which
# version of which rule produced it (rule configuration and versioning, Stage C).
RULE_VERSIONS: dict[str, int] = {
    "critical_health": 1,
    "health_decline": 1,
    "inspection_gap": 2,  # v2: completed inspections and issue activity count as attention; structured evidence
    "irrigation_defer": 1,
    "symptom_cluster": 1,
}


@dataclass(frozen=True)
class HealthPoint:
    observed_at: datetime
    score: float  # 0..100


@dataclass(frozen=True)
class WaterTask:
    """An open watering task: the thing an irrigation-deferral suggestion would postpone."""

    task_id: str
    key: str
    status: str  # todo | in_progress | blocked
    due_at: datetime | None


@dataclass(frozen=True)
class AssetSnapshot:
    asset_id: str
    label: str
    zone: str | None
    last_observed_at: datetime | None
    health_history: tuple[HealthPoint, ...] = ()
    latest_symptoms: tuple[str, ...] = ()
    # --- operational context (defaults keep older callers valid) ---
    registered_at: datetime | None = None  # a just-registered asset is not "overdue"
    latest_health_score: float | None = None
    latest_observation_id: str | None = None
    open_issue_count: int = 0
    has_open_inspection_task: bool = False
    # The decline baseline restarts when an issue for this asset is resolved: what was handled is not re-flagged.
    last_resolved_at: datetime | None = None
    # --- attention signals besides observations (an inspection task that was completed, work on an open issue) ---
    last_inspection_completed_at: datetime | None = None
    last_issue_activity_at: datetime | None = None
    # --- irrigation context (only filled for assets that have an open watering task) ---
    latitude: float | None = None
    longitude: float | None = None
    position_source: str | None = None  # "asset" | "location"
    open_water_tasks: tuple[WaterTask, ...] = ()
    last_watered_at: datetime | None = None  # completion of the most recent watering task
    water_stress_signs: tuple[str, ...] = ()  # recorded symptoms / open issue categories pointing at water stress
    weather: WeatherContext | None = None
    weather_status: str = "not_needed"  # not_needed | ok | unavailable | no_location


@dataclass(frozen=True)
class Skip:
    """A case a rule looked at and deliberately did NOT turn into a suggestion, with the reason (run diagnostics)."""

    asset_id: str
    rule_key: str
    reason: str


@dataclass(frozen=True)
class Finding:
    rule_key: str
    method: str  # "rule" | "statistical"
    subject_ids: tuple[str, ...]
    title: str
    explanation: str
    severity: str  # low | medium | high | critical
    proposed_action: dict = field(default_factory=dict)
    # Structured inputs behind the finding (values, thresholds, provenance). Stored on the recommendation so anyone can
    # see exactly what the rule saw; `explanation` stays a short human sentence.
    evidence: dict = field(default_factory=dict)
    # Overrides the default `<rule_key>:<asset ids>` when one asset can have several independent suggestions.
    subject_key: str | None = None

    @property
    def dedupe_key(self) -> str:
        return f"{self.rule_key}:{self.subject_key or ','.join(sorted(self.subject_ids))}"


class Rule(Protocol):
    @property
    def key(self) -> str: ...

    def evaluate(self, assets: list[AssetSnapshot], now: datetime) -> list[Finding]: ...
