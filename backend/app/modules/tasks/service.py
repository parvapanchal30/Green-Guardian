from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import Forbidden, NotFound, Unprocessable
from app.core.pagination import Page, PageParams
from app.core.timeutil import utcnow
from app.modules.assets.service import get_asset
from app.modules.assets.state import refresh_counts
from app.modules.audit import service as audit
from app.modules.intelligence.models import Outcome
from app.modules.intelligence.outcomes import record_outcome
from app.modules.issues.service import get_issue
from app.modules.locations.service import get_location
from app.modules.observations.models import ObservationKind
from app.modules.observations.schemas import ObservationCreate
from app.modules.observations.service import create_observation
from app.modules.workspaces.keys import next_key
from app.modules.workspaces.members import ensure_member
from app.modules.workspaces.models import Role

from . import workflow
from .mapping import load_task_outs
from .models import OPEN_TASK_STATUSES, Task, TaskSource, TaskStatus, TaskStatusHistory, TaskType
from .schemas import TaskCreate, TaskDetail, TaskHistoryOut, TaskOut, TaskTransition, TaskUpdate


def get_task(db: Session, ctx: WorkspaceContext, task_id: uuid.UUID, *, lock: bool = False) -> Task:
    q = select(Task).where(Task.id == task_id, Task.workspace_id == ctx.workspace_id)
    if lock:
        q = q.with_for_update()
    task = db.scalar(q)
    if task is None:
        raise NotFound("Task not found", code="task_not_found")
    return task


def _history(
    db: Session, ctx: WorkspaceContext, task: Task, from_status: str | None, to_status: str, note: str | None
) -> None:
    db.add(
        TaskStatusHistory(
            workspace_id=ctx.workspace_id,
            task_id=task.id,
            from_status=from_status,
            to_status=to_status,
            actor_id=ctx.user.id,
            note=note,
        )
    )


def detail(db: Session, ctx: WorkspaceContext, task: Task) -> TaskDetail:
    out = load_task_outs(db, ctx.workspace_id, [task])[0]
    history = db.scalars(
        select(TaskStatusHistory)
        .where(TaskStatusHistory.workspace_id == ctx.workspace_id, TaskStatusHistory.task_id == task.id)
        .order_by(TaskStatusHistory.at, TaskStatusHistory.id)
    ).all()
    return TaskDetail(
        **out.model_dump(),
        history=[
            TaskHistoryOut(from_status=h.from_status, to_status=h.to_status, actor_id=h.actor_id, note=h.note, at=h.at)
            for h in history
        ],
        allowed_transitions=list(workflow.allowed(task.status)),
    )


def reschedule_task(
    db: Session, ctx: WorkspaceContext, task: Task, due_at, note: str, *, source: str = "manual"
) -> None:
    """Move an open task's due date. Recorded in the task history (as a same-status entry, like other field changes) so
    the change is traceable; the caller commits and audits."""
    old = task.due_at
    task.due_at = due_at
    task.version += 1
    _history(
        db,
        ctx,
        task,
        task.status,
        task.status,
        f"{note} (due {old.isoformat() if old else 'unset'} -> {due_at.isoformat()})",
    )


def create_task_entity(
    db: Session,
    ctx: WorkspaceContext,
    data: TaskCreate,
    *,
    source: TaskSource | None = None,
    recommendation_id: uuid.UUID | None = None,
) -> Task:
    """Create a task (flush, no commit). Used by the API and by accepting a recommendation."""
    asset_id, location_id = data.asset_id, data.location_id
    issue = get_issue(db, ctx, data.issue_id) if data.issue_id else None
    if issue is not None:
        if issue.resolved_at is not None:
            raise Unprocessable("cannot add a task to a closed issue; reopen it first", code="issue_closed")
        if asset_id and issue.asset_id and asset_id != issue.asset_id:
            raise Unprocessable("asset_id differs from the issue's asset", code="asset_mismatch")
        asset_id = asset_id or issue.asset_id
        location_id = location_id or issue.location_id
    if asset_id:
        get_asset(db, ctx, asset_id)
    if location_id:
        get_location(db, ctx, location_id)
    ensure_member(db, ctx, data.assignee_id)

    task = Task(
        workspace_id=ctx.workspace_id,
        key=next_key(db, ctx.workspace_id, "task", "T"),
        type=data.type.value,
        title=data.title,
        description=data.description,
        issue_id=issue.id if issue else None,
        asset_id=asset_id,
        location_id=location_id,
        assignee_id=data.assignee_id,
        created_by=ctx.user.id,
        priority=data.priority.value,
        status=TaskStatus.TODO.value,
        source=(source or (TaskSource.ISSUE if issue else TaskSource.MANUAL)).value,
        recommendation_id=recommendation_id,
        due_at=data.due_at,
    )
    db.add(task)
    db.flush()
    _history(db, ctx, task, None, task.status, "Task created")
    if asset_id:
        refresh_counts(db, ctx.workspace_id, asset_id)
    return task


def create_task(db: Session, ctx: WorkspaceContext, data: TaskCreate) -> TaskDetail:
    task = create_task_entity(db, ctx, data)
    audit.record_ctx(
        db,
        ctx,
        "task.create",
        target_type="task",
        target_id=task.id,
        details={
            "key": task.key,
            "type": task.type,
            "priority": task.priority,
            "asset_id": task.asset_id,
            "issue_id": task.issue_id,
            "assignee_id": task.assignee_id,
        },
    )
    db.commit()
    return detail(db, ctx, task)


def list_tasks(
    db: Session,
    ctx: WorkspaceContext,
    page: PageParams,
    *,
    status: TaskStatus | None = None,
    is_open: bool | None = None,
    assignee: str | None = None,
    issue_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    type: TaskType | None = None,  # noqa: A002 - mirrors the query parameter name
    overdue: bool | None = None,
    q: str | None = None,
) -> Page[TaskOut]:
    stmt = select(Task).where(Task.workspace_id == ctx.workspace_id)
    open_values = [s.value for s in OPEN_TASK_STATUSES]
    if status:
        stmt = stmt.where(Task.status == status.value)
    if is_open is True:
        stmt = stmt.where(Task.status.in_(open_values))
    if is_open is False:
        stmt = stmt.where(Task.status.not_in(open_values))
    if assignee == "me":
        stmt = stmt.where(Task.assignee_id == ctx.user.id)
    elif assignee == "unassigned":
        stmt = stmt.where(Task.assignee_id.is_(None))
    elif assignee:
        try:
            stmt = stmt.where(Task.assignee_id == uuid.UUID(assignee))
        except ValueError as e:
            raise Unprocessable("assignee must be 'me', 'unassigned' or a user id", code="bad_assignee") from e
    if issue_id:
        stmt = stmt.where(Task.issue_id == issue_id)
    if asset_id:
        stmt = stmt.where(Task.asset_id == asset_id)
    if type:
        stmt = stmt.where(Task.type == type.value)
    if overdue is True:
        stmt = stmt.where(Task.status.in_(open_values), Task.due_at.is_not(None), Task.due_at < utcnow())
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(Task.title).like(like), func.lower(Task.key).like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    # nearest due date first, tasks without a due date last
    rows = db.scalars(
        stmt.order_by(Task.due_at.is_(None), Task.due_at, Task.priority, Task.created_at, Task.id)
        .limit(page.limit)
        .offset(page.offset)
    ).all()
    return Page(
        items=load_task_outs(db, ctx.workspace_id, list(rows)), total=total, limit=page.limit, offset=page.offset
    )


def get_detail(db: Session, ctx: WorkspaceContext, task_id: uuid.UUID) -> TaskDetail:
    return detail(db, ctx, get_task(db, ctx, task_id))


def update_task(db: Session, ctx: WorkspaceContext, task_id: uuid.UUID, data: TaskUpdate) -> TaskDetail:
    task = get_task(db, ctx, task_id, lock=True)
    sent = data.model_fields_set
    changes: list[str] = []
    if "title" in sent and data.title and data.title != task.title:
        changes.append("title changed")
        task.title = data.title
    if "description" in sent and data.description != task.description:
        changes.append("description changed")
        task.description = data.description
    if "priority" in sent and data.priority and data.priority.value != task.priority:
        changes.append(f"priority {task.priority} → {data.priority.value}")
        task.priority = data.priority.value
    if "due_at" in sent and data.due_at != task.due_at:
        changes.append("due date changed" if data.due_at else "due date removed")
        task.due_at = data.due_at
    if "assignee_id" in sent and data.assignee_id != task.assignee_id:
        ensure_member(db, ctx, data.assignee_id)
        changes.append("reassigned" if data.assignee_id else "unassigned")
        task.assignee_id = data.assignee_id
    if changes:
        task.version += 1
        _history(db, ctx, task, task.status, task.status, "; ".join(changes))  # audited like a state change
        audit.record_ctx(
            db, ctx, "task.update", target_type="task", target_id=task.id, details={"key": task.key, "changes": changes}
        )
    db.commit()
    return detail(db, ctx, task)


def transition(db: Session, ctx: WorkspaceContext, task_id: uuid.UUID, data: TaskTransition) -> TaskDetail:
    task = get_task(db, ctx, task_id, lock=True)
    to_status = data.to_status.value
    workflow.check(task.status, to_status)

    is_assignee = task.assignee_id == ctx.user.id
    if not (ctx.has_role(Role.MANAGER) or (is_assignee and ctx.has_role(Role.WORKER))):
        raise Forbidden("only the assignee or a manager can change this task's status", code="not_assignee")
    if (task.status, to_status) in workflow.REOPENING and not ctx.has_role(Role.MANAGER):
        raise Forbidden("only a manager can reopen a task", code="insufficient_role")
    if data.observation is not None and to_status != TaskStatus.DONE.value:
        raise Unprocessable(
            "a follow-up observation can only be recorded when completing a task", code="observation_needs_done"
        )
    if data.observation is not None and task.asset_id is None:
        raise Unprocessable("this task has no asset to observe", code="task_has_no_asset")

    now = utcnow()
    from_status = task.status
    task.status = to_status
    task.version += 1
    if to_status == TaskStatus.IN_PROGRESS.value and task.started_at is None:
        task.started_at = now
    if to_status == TaskStatus.DONE.value:
        task.completed_at = now
        task.completion_notes = data.note or task.completion_notes
    elif from_status == TaskStatus.DONE.value:
        task.completed_at = None  # reopened
    _history(db, ctx, task, from_status, to_status, data.note)

    if data.observation is not None and task.asset_id is not None:
        # ACT -> UPDATE ASSET: completing the work records what was found, which updates the asset's state.
        create_observation(
            db,
            ctx,
            ObservationCreate(
                asset_id=task.asset_id,
                kind=ObservationKind.HEALTH,
                health_score=data.observation.health_score,
                symptoms=data.observation.symptoms,
                notes=data.observation.notes or f"Follow-up recorded when completing {task.key}",
                attachments=data.observation.attachments,
            ),
            commit=False,
        )
    if task.asset_id:
        refresh_counts(db, ctx.workspace_id, task.asset_id)
    if to_status in (TaskStatus.DONE.value, TaskStatus.CANCELLED.value):  # follow-up for the suggestion behind it
        record_outcome(
            db,
            ctx.workspace_id,
            task.recommendation_id,
            Outcome.TASK_COMPLETED if to_status == TaskStatus.DONE.value else Outcome.TASK_CANCELLED,
            detail=f"task {task.key} {to_status}",
            at=now,
        )
    audit.record_ctx(
        db,
        ctx,
        "task.transition",
        target_type="task",
        target_id=task.id,
        details={
            "key": task.key,
            "from": from_status,
            "to": to_status,
            "follow_up_observation": data.observation is not None,
        },
    )
    db.commit()
    return detail(db, ctx, task)
