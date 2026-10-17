"""Follow-up: record what eventually happened to the work a recommendation led to.

Depends only on the models, so the task and issue services can call it without importing the agent (which imports
them). The first outcome wins: a later change (a reopened task, a re-resolved issue) never rewrites history; the
task/issue history and the audit trail keep the full story.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow

from .models import Outcome, Recommendation


def record_outcome(
    db: Session,
    workspace_id: uuid.UUID,
    recommendation_id: uuid.UUID | None,
    outcome: Outcome,
    *,
    detail: str | None = None,
    at: datetime | None = None,
) -> bool:
    """Set the outcome of `recommendation_id` (if it exists in this workspace and has none yet). Does not commit."""
    if recommendation_id is None:
        return False
    rec = db.scalar(
        select(Recommendation).where(
            Recommendation.id == recommendation_id, Recommendation.workspace_id == workspace_id
        )
    )
    if rec is None or rec.outcome is not None:
        return False
    rec.outcome = outcome.value
    rec.outcome_at = at or utcnow()
    rec.outcome_detail = (detail or "")[:500] or None
    return True
