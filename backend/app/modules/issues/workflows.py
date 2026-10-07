"""Issue workflows as data (ADR-011): states, allowed transitions and terminal states per workflow.

A workflow is chosen from the issue category (and the workspace mode), so new kinds of issue (irrigation failure,
pest outbreak, harvest readiness, infrastructure fault) are a new entry here, not a schema or engine change.
The engine below is generic; it knows nothing about plants.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.core.errors import Conflict

from .models import IssueCategory

WONT_FIX = "closed_wont_fix"


@dataclass(frozen=True)
class Workflow:
    key: str
    label: str
    states: tuple[str, ...]
    initial: str
    transitions: Mapping[str, tuple[str, ...]]
    terminal: frozenset[str]  # entering one closes the issue (resolved_at is set)
    success: frozenset[str]  # terminal states that mean "the problem is dealt with" (the rest are "won't fix")

    def allowed(self, state: str) -> tuple[str, ...]:
        return self.transitions.get(state, ())

    def is_terminal(self, state: str) -> bool:
        return state in self.terminal

    def check(self, from_state: str, to_state: str) -> None:
        if to_state not in self.states:
            raise Conflict(
                f"'{to_state}' is not a state of workflow '{self.key}'",
                code="unknown_state",
                extra={"states": list(self.states)},
            )
        if to_state not in self.allowed(from_state):
            raise Conflict(
                f"cannot move from '{from_state}' to '{to_state}'",
                code="invalid_transition",
                extra={"allowed": list(self.allowed(from_state))},
            )


PLANT_HEALTH = Workflow(
    key="plant_health",
    label="Plant health",
    states=("open", "investigating", "treatment", "monitoring", "resolved", WONT_FIX),
    initial="open",
    transitions={
        "open": ("investigating", "resolved", WONT_FIX),
        "investigating": ("open", "treatment", "monitoring", "resolved", WONT_FIX),
        "treatment": ("investigating", "monitoring", "resolved", WONT_FIX),
        "monitoring": ("treatment", "investigating", "resolved", WONT_FIX),
        "resolved": ("investigating",),  # reopen
        WONT_FIX: ("open",),
    },
    terminal=frozenset({"resolved", WONT_FIX}),
    success=frozenset({"resolved"}),
)

FIELD_DISEASE = Workflow(
    key="field_disease",
    label="Field disease",
    states=("open", "field_inspection", "treatment", "monitoring", "resolved", WONT_FIX),
    initial="open",
    transitions={
        "open": ("field_inspection", "resolved", WONT_FIX),
        "field_inspection": ("open", "treatment", "monitoring", "resolved", WONT_FIX),
        "treatment": ("field_inspection", "monitoring", "resolved", WONT_FIX),
        "monitoring": ("treatment", "field_inspection", "resolved", WONT_FIX),
        "resolved": ("field_inspection",),
        WONT_FIX: ("open",),
    },
    terminal=frozenset({"resolved", WONT_FIX}),
    success=frozenset({"resolved"}),
)

INFRASTRUCTURE = Workflow(
    key="infrastructure",
    label="Infrastructure",
    states=("open", "assigned", "fixed", "verified", WONT_FIX),
    initial="open",
    transitions={
        "open": ("assigned", WONT_FIX),
        "assigned": ("open", "fixed", WONT_FIX),
        "fixed": ("assigned", "verified"),
        "verified": ("assigned",),
        WONT_FIX: ("open",),
    },
    terminal=frozenset({"verified", WONT_FIX}),
    success=frozenset({"verified"}),
)

HARVEST_READINESS = Workflow(
    key="harvest_readiness",
    label="Harvest readiness",
    states=("pending", "inspection", "ready", "harvested", WONT_FIX),
    initial="pending",
    transitions={
        "pending": ("inspection", WONT_FIX),
        "inspection": ("pending", "ready", WONT_FIX),
        "ready": ("inspection", "harvested", WONT_FIX),
        "harvested": ("ready",),
        WONT_FIX: ("pending",),
    },
    terminal=frozenset({"harvested", WONT_FIX}),
    success=frozenset({"harvested"}),
)

WORKFLOWS: dict[str, Workflow] = {w.key: w for w in (PLANT_HEALTH, FIELD_DISEASE, INFRASTRUCTURE, HARVEST_READINESS)}


def workflow_for(category: IssueCategory | str, workspace_mode: str) -> Workflow:
    cat = IssueCategory(category)
    if cat in (IssueCategory.IRRIGATION_FAILURE, IssueCategory.MAINTENANCE):
        return INFRASTRUCTURE
    if cat == IssueCategory.HARVEST_READINESS:
        return HARVEST_READINESS
    if workspace_mode == "agricultural_production" and cat in (IssueCategory.DISEASE, IssueCategory.PEST):
        return FIELD_DISEASE
    return PLANT_HEALTH
