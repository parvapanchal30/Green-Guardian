"""Did the work on an issue help? A deterministic RULE over recorded observations (ADR-059).

It compares health scores that people recorded; it does not diagnose the plant, and "improved" means only that the
latest recorded score after the work is at least MIN_CHANGE points higher than the latest one before it. When scores
are missing it says so ("observed_without_score") instead of guessing.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import as_utc
from app.modules.issues.models import Issue, ResolutionOutcome
from app.modules.observations.models import Observation

from .models import ActionRecord
from .schemas import Verification, VerificationStatus

MIN_CHANGE = 5.0
# Workflows whose success needs evidence that the plant was looked at after the work. Infrastructure has its own
# "verified" state and harvest readiness ends in a harvest, so neither is covered by this rule.
VERIFIED_WORKFLOWS = frozenset({"plant_health", "field_disease"})
SUCCESS_OUTCOMES = frozenset({ResolutionOutcome.FIXED.value, ResolutionOutcome.MITIGATED.value})


def effective_actions(db: Session, workspace_id: uuid.UUID, issue_id: uuid.UUID) -> list[ActionRecord]:
    """The actions on an issue that count: not replaced by a correction and not withdrawn."""
    replaced = select(ActionRecord.supersedes_id).where(
        ActionRecord.workspace_id == workspace_id, ActionRecord.supersedes_id.is_not(None)
    )
    return list(
        db.scalars(
            select(ActionRecord)
            .where(
                ActionRecord.workspace_id == workspace_id,
                ActionRecord.issue_id == issue_id,
                ActionRecord.withdrawn.is_(False),
                ActionRecord.id.not_in(replaced),
            )
            .order_by(ActionRecord.performed_at)
        )
    )


def requires_follow_up(issue: Issue, outcome: str) -> bool:
    return issue.asset_id is not None and issue.workflow_key in VERIFIED_WORKFLOWS and outcome in SUCCESS_OUTCOMES


def compute(db: Session, issue: Issue, *, until: datetime | None = None) -> Verification:
    """`until` bounds the follow-up window (default: the closing time of a closed issue, otherwise open-ended)."""
    required = issue.asset_id is not None and issue.workflow_key in VERIFIED_WORKFLOWS
    if issue.asset_id is None:
        return Verification(
            status="not_applicable",
            min_change=MIN_CHANGE,
            actions=0,
            last_action_at=None,
            baseline_score=None,
            baseline_at=None,
            follow_up_score=None,
            follow_up_at=None,
            change=None,
            required_for_success=False,
        )
    end = until or issue.resolved_at
    actions = [
        a
        for a in effective_actions(db, issue.workspace_id, issue.id)
        if end is None or as_utc(a.performed_at) <= as_utc(end)
    ]
    first_at = actions[0].performed_at if actions else None
    last_at = actions[-1].performed_at if actions else None

    superseded = select(Observation.supersedes_id).where(
        Observation.workspace_id == issue.workspace_id, Observation.supersedes_id.is_not(None)
    )
    of_asset = (
        Observation.workspace_id == issue.workspace_id,
        Observation.asset_id == issue.asset_id,
        Observation.id.not_in(superseded),
    )
    # Baseline: strictly before the first action, or up to the opening when nothing has been done yet.
    before = Observation.observed_at < first_at if first_at else Observation.observed_at <= issue.opened_at
    baseline = db.scalar(
        select(Observation)
        .where(*of_asset, before, Observation.health_score.is_not(None))
        .order_by(Observation.observed_at.desc(), Observation.created_at.desc())
        .limit(1)
    )
    # Follow-up: at or after the last action (a check recorded when the work is completed counts), or strictly after
    # the opening when nothing was done.
    after = Observation.observed_at >= last_at if last_at else Observation.observed_at > issue.opened_at
    window = (*of_asset, after, *((Observation.observed_at <= end,) if end else ()))
    latest = db.scalar(
        select(Observation)
        .where(*window)
        .order_by(Observation.observed_at.desc(), Observation.created_at.desc())
        .limit(1)
    )
    scored = db.scalar(
        select(Observation)
        .where(*window, Observation.health_score.is_not(None))
        .order_by(Observation.observed_at.desc(), Observation.created_at.desc())
        .limit(1)
    )

    change: float | None = None
    status: VerificationStatus
    if latest is None:
        status = "awaiting_follow_up"
    elif (
        scored is not None
        and baseline is not None
        and scored.health_score is not None
        and baseline.health_score is not None
    ):
        change = round(scored.health_score - baseline.health_score, 1)
        status = "improved" if change >= MIN_CHANGE else "worse" if change <= -MIN_CHANGE else "unchanged"
    else:
        status = "observed_without_score"
    return Verification(
        status=status,
        min_change=MIN_CHANGE,
        actions=len(actions),
        last_action_at=as_utc(last_at) if last_at else None,
        baseline_score=baseline.health_score if baseline else None,
        baseline_at=as_utc(baseline.observed_at) if baseline else None,
        follow_up_score=scored.health_score if scored else None,
        follow_up_at=as_utc(latest.observed_at) if latest else None,
        change=change,
        required_for_success=required,
    )
