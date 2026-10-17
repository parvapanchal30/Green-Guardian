"""ORM -> API mapping for tasks, shared by the tasks and issues modules (kept free of services to avoid cycles)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import as_utc, utcnow
from app.modules.assets.models import BiologicalAsset
from app.modules.issues.models import Issue

from .models import OPEN_TASK_STATUSES, Priority, Task, TaskSource, TaskStatus, TaskType
from .schemas import TaskOut


def _overdue(task: Task, now: datetime) -> bool:
    return (
        task.due_at is not None and task.status in [s.value for s in OPEN_TASK_STATUSES] and as_utc(task.due_at) < now
    )


def load_task_outs(db: Session, workspace_id: uuid.UUID, tasks: list[Task]) -> list[TaskOut]:
    """Map tasks to API objects with two batched lookups (issue keys, asset labels): no N+1 queries."""
    issue_ids = {t.issue_id for t in tasks if t.issue_id}
    asset_ids = {t.asset_id for t in tasks if t.asset_id}
    keys = (
        dict(
            db.execute(
                select(Issue.id, Issue.key).where(Issue.workspace_id == workspace_id, Issue.id.in_(issue_ids))
            ).all()
        )
        if issue_ids
        else {}
    )
    labels = (
        dict(
            db.execute(
                select(BiologicalAsset.id, BiologicalAsset.label).where(
                    BiologicalAsset.workspace_id == workspace_id, BiologicalAsset.id.in_(asset_ids)
                )
            ).all()
        )
        if asset_ids
        else {}
    )
    now = utcnow()
    return [
        TaskOut(
            id=t.id,
            key=t.key,
            type=TaskType(t.type),
            title=t.title,
            description=t.description,
            issue_id=t.issue_id,
            issue_key=keys.get(t.issue_id) if t.issue_id else None,
            asset_id=t.asset_id,
            asset_label=labels.get(t.asset_id) if t.asset_id else None,
            location_id=t.location_id,
            assignee_id=t.assignee_id,
            priority=Priority(t.priority),
            status=TaskStatus(t.status),
            source=TaskSource(t.source),
            recommendation_id=t.recommendation_id,
            due_at=t.due_at,
            started_at=t.started_at,
            completed_at=t.completed_at,
            completion_notes=t.completion_notes,
            overdue=_overdue(t, now),
            created_at=t.created_at,
            updated_at=t.updated_at,
            version=t.version,
        )
        for t in tasks
    ]
