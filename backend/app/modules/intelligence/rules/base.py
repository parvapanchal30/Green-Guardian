"""Rule interface for the Botanical Operations Agent (method = RULE).

Pure functions over plain data: no DB, no I/O. Rules never write; they return Findings
that a service later persists as deduplicated Recommendations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class HealthPoint:
    observed_at: datetime
    score: float  # 0..100


@dataclass(frozen=True)
class AssetSnapshot:
    asset_id: str
    label: str
    zone: str | None
    last_observed_at: datetime | None
    health_history: tuple[HealthPoint, ...] = ()
    latest_symptoms: tuple[str, ...] = ()


@dataclass(frozen=True)
class Finding:
    rule_key: str
    method: str  # "rule" | "statistical"
    subject_ids: tuple[str, ...]
    title: str
    explanation: str
    severity: str  # low | medium | high | critical
    proposed_action: dict = field(default_factory=dict)

    @property
    def dedupe_key(self) -> str:
        return f"{self.rule_key}:{','.join(sorted(self.subject_ids))}"


class Rule(Protocol):
    key: str

    def evaluate(self, assets: list[AssetSnapshot], now: datetime) -> list[Finding]: ...
