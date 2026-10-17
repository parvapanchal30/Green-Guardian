"""Acting on recommendations. A person decides; the proposal is only a default. Accepting goes through the normal
issue/task services, so every invariant, history row and permission rule applies exactly as for a manual action."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import AppError, Conflict, NotFound, Unprocessable
from app.core.pagination import Page, PageParams
from app.core.timeutil import as_utc, utcnow
from app.modules.audit import service as audit
from app.modules.issues.models import IssueCategory, IssueSource, Severity
from app.modules.issues.schemas import IssueCreate
from app.modules.issues.service import create_issue_entity
from app.modules.tasks.models import Priority, TaskSource, TaskType
from app.modules.tasks.schemas import TaskCreate
from app.modules.tasks.service import create_task_entity, get_task, reschedule_task

from . import runs
from .models import AgentRun, Outcome, Recommendation, RecommendationStatus, RunTrigger
from .ports import WeatherContextProvider
from .schemas import (
    AcceptRecommendation,
    AgentRunOut,
    AgentRunRecord,
    DismissRecommendation,
    RecommendationOut,
    RuleInfo,
)

DEFAULT_INSPECTION_DUE = timedelta(days=3)


def get_recommendation(db: Session, ctx: WorkspaceContext, rec_id: uuid.UUID, *, lock: bool = False) -> Recommendation:
    q = select(Recommendation).where(Recommendation.id == rec_id, Recommendation.workspace_id == ctx.workspace_id)
    if lock:
        q = q.with_for_update()
    rec = db.scalar(q)
    if rec is None:
        raise NotFound("Recommendation not found", code="recommendation_not_found")
    return rec


class AgentRunFailed(AppError):
    status, code = 500, "agent_run_failed"


def to_record(run: AgentRun) -> AgentRunRecord:
    duration = (as_utc(run.finished_at) - as_utc(run.started_at)).total_seconds() if run.finished_at else None
    return AgentRunRecord(
        id=run.id,
        trigger=run.trigger,
        status=run.status,
        requested_by=run.requested_by,
        worker_id=run.worker_id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_s=None if duration is None else round(duration, 3),
        evaluated_assets=run.evaluated_assets,
        findings=run.findings,
        recommendations_created=run.recommendations_created,
        recommendations_expired=run.recommendations_expired,
        rules=run.rules,
        diagnostics=run.diagnostics,
        error=run.error,
    )


def run(db: Session, ctx: WorkspaceContext, weather: WeatherContextProvider | None = None) -> AgentRunOut:
    """A manual run: the same code path as a scheduled one, recorded in the run history. Refused while another run
    (manual or scheduled) is in progress for this workspace."""
    claimed = runs.claim(db, ctx.workspace_id, RunTrigger.MANUAL, requested_by=ctx.user.id)
    if claimed is None:
        raise Conflict("An agent run is already in progress for this workspace", code="agent_run_in_progress")
    finished, result = runs.execute(db, claimed, ctx.workspace.settings, weather=weather)
    if result is None:
        raise AgentRunFailed("The agent run failed. See the run history for the reason.")
    return AgentRunOut(
        run=to_record(finished),
        evaluated_assets=result.evaluated,
        created=[RecommendationOut.model_validate(r) for r in result.created],
        expired=result.expired,
        rules=[RuleInfo(**r) for r in result.rules],
    )


def list_runs(db: Session, ctx: WorkspaceContext, page: PageParams) -> Page[AgentRunRecord]:
    q = select(AgentRun).where(AgentRun.workspace_id == ctx.workspace_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(AgentRun.started_at.desc(), AgentRun.id.desc()).limit(page.limit).offset(page.offset))
    return Page(items=[to_record(r) for r in rows], total=total, limit=page.limit, offset=page.offset)


def get_run(db: Session, ctx: WorkspaceContext, run_id: uuid.UUID) -> AgentRunRecord:
    row = db.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.workspace_id == ctx.workspace_id))
    if row is None:
        raise NotFound("Agent run not found", code="agent_run_not_found")
    return to_record(row)


def list_recommendations(
    db: Session,
    ctx: WorkspaceContext,
    page: PageParams,
    *,
    status: RecommendationStatus | None = RecommendationStatus.OPEN,
    asset_id: uuid.UUID | None = None,
) -> Page[RecommendationOut]:
    q = select(Recommendation).where(Recommendation.workspace_id == ctx.workspace_id)
    if status:
        q = q.where(Recommendation.status == status.value)
    if asset_id:
        q = q.where(Recommendation.asset_id == asset_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(
        q.order_by(Recommendation.created_at.desc(), Recommendation.id).limit(page.limit).offset(page.offset)
    )
    return Page(
        items=[RecommendationOut.model_validate(r) for r in rows], total=total, limit=page.limit, offset=page.offset
    )


def accept(db: Session, ctx: WorkspaceContext, rec_id: uuid.UUID, data: AcceptRecommendation) -> RecommendationOut:
    rec = get_recommendation(db, ctx, rec_id, lock=True)
    if rec.status != RecommendationStatus.OPEN.value:
        raise Conflict(f"recommendation is already {rec.status}", code="recommendation_not_open")
    action = rec.proposed_action or {}
    kind = action.get("create")
    now = utcnow()

    if kind == "task":
        task = create_task_entity(
            db,
            ctx,
            TaskCreate(
                title=f"Inspect {rec.title.split(' has ')[0]}" if action.get("type") == "inspect" else rec.title,
                type=TaskType(action.get("type", "inspect")),
                description=f"Created from recommendation: {rec.explanation}",
                asset_id=rec.asset_id,
                assignee_id=data.assignee_id,
                priority=Priority.P2,
                due_at=data.due_at or now + DEFAULT_INSPECTION_DUE,
            ),
            source=TaskSource.AGENT,
            recommendation_id=rec.id,
        )
        rec.accepted_entity_type, rec.accepted_entity_id = "task", task.id
    elif kind == "defer_task":
        # Advisory irrigation deferral: move the due date of a watering task that has not started. The person decides
        # (this is the accept click); the system never reschedules work on its own.
        task = get_task(db, ctx, uuid.UUID(str(action["task_id"])), lock=True)
        if task.status != "todo":
            raise Conflict(
                f"task {task.key} is {task.status}; a deferral only applies to a task that has not started",
                code="task_not_deferrable",
            )
        base = max(as_utc(task.due_at), now) if task.due_at else now
        new_due = data.due_at or base + timedelta(hours=int(action.get("defer_hours", 24)))
        reschedule_task(db, ctx, task, new_due, f"Deferred on advice {rec.rule_key}: {rec.title}", source="agent")
        rec.accepted_entity_type, rec.accepted_entity_id = "task", task.id
        rec.outcome, rec.outcome_at = Outcome.DEFERRAL_APPLIED.value, now
        rec.outcome_detail = f"task {task.key} due date moved to {new_due.isoformat()}"
    elif kind == "issue":
        severity = Severity(data.severity or rec.severity)
        obs_id = action.get("observation_id")
        issue = create_issue_entity(
            db,
            ctx,
            IssueCreate(
                title=rec.title,
                description=f"Opened from a rule-based recommendation: {rec.explanation}",
                category=IssueCategory(action.get("category", "other")),
                severity=severity,
                asset_id=rec.asset_id,
                observation_id=uuid.UUID(obs_id) if obs_id else None,
                assignee_id=data.assignee_id,
            ),
            source=IssueSource.AGENT,
            recommendation_id=rec.id,
        )
        rec.accepted_entity_type, rec.accepted_entity_id = "issue", issue.id
    else:
        raise Unprocessable(f"recommendation proposes an unsupported action {kind!r}", code="unsupported_action")

    rec.status = RecommendationStatus.ACCEPTED.value
    rec.decided_by, rec.decided_at = ctx.user.id, now
    audit.record_ctx(
        db,
        ctx,
        "recommendation.accept",
        target_type="recommendation",
        target_id=rec.id,
        details={"rule": rec.rule_key, "created": rec.accepted_entity_type, "created_id": rec.accepted_entity_id},
    )
    db.commit()
    return RecommendationOut.model_validate(rec)


def dismiss(db: Session, ctx: WorkspaceContext, rec_id: uuid.UUID, data: DismissRecommendation) -> RecommendationOut:
    rec = get_recommendation(db, ctx, rec_id, lock=True)
    if rec.status != RecommendationStatus.OPEN.value:
        raise Conflict(f"recommendation is already {rec.status}", code="recommendation_not_open")
    rec.status = RecommendationStatus.DISMISSED.value
    rec.dismissed_reason = data.reason
    rec.decided_by, rec.decided_at = ctx.user.id, utcnow()
    audit.record_ctx(
        db,
        ctx,
        "recommendation.dismiss",
        target_type="recommendation",
        target_id=rec.id,
        details={"rule": rec.rule_key, "reason": data.reason},
    )
    db.commit()
    return RecommendationOut.model_validate(rec)
