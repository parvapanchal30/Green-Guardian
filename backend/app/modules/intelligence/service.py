"""Acting on recommendations. A person decides; the proposal is only a default. Accepting goes through the normal
issue/task services, so every invariant, history row and permission rule applies exactly as for a manual action."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import Conflict, NotFound, Unprocessable
from app.core.pagination import Page, PageParams
from app.core.timeutil import utcnow
from app.modules.issues.models import IssueCategory, IssueSource, Severity
from app.modules.issues.schemas import IssueCreate
from app.modules.issues.service import create_issue_entity
from app.modules.tasks.models import Priority, TaskSource, TaskType
from app.modules.tasks.schemas import TaskCreate
from app.modules.tasks.service import create_task_entity

from . import runner
from .models import Recommendation, RecommendationStatus
from .schemas import AcceptRecommendation, AgentRunOut, DismissRecommendation, RecommendationOut, RuleInfo

DEFAULT_INSPECTION_DUE = timedelta(days=3)


def get_recommendation(db: Session, ctx: WorkspaceContext, rec_id: uuid.UUID, *, lock: bool = False) -> Recommendation:
    q = select(Recommendation).where(Recommendation.id == rec_id, Recommendation.workspace_id == ctx.workspace_id)
    if lock:
        q = q.with_for_update()
    rec = db.scalar(q)
    if rec is None:
        raise NotFound("Recommendation not found", code="recommendation_not_found")
    return rec


def run(db: Session, ctx: WorkspaceContext) -> AgentRunOut:
    evaluated, created = runner.evaluate(db, ctx)
    db.commit()
    cfg = runner.AgentSettings.from_workspace(ctx.workspace.settings)
    return AgentRunOut(
        evaluated_assets=evaluated,
        created=[RecommendationOut.model_validate(r) for r in created],
        rules=[RuleInfo(**r) for r in runner.describe_rules(cfg)],
    )


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
    db.commit()
    return RecommendationOut.model_validate(rec)


def dismiss(db: Session, ctx: WorkspaceContext, rec_id: uuid.UUID, data: DismissRecommendation) -> RecommendationOut:
    rec = get_recommendation(db, ctx, rec_id, lock=True)
    if rec.status != RecommendationStatus.OPEN.value:
        raise Conflict(f"recommendation is already {rec.status}", code="recommendation_not_open")
    rec.status = RecommendationStatus.DISMISSED.value
    rec.dismissed_reason = data.reason
    rec.decided_by, rec.decided_at = ctx.user.id, utcnow()
    db.commit()
    return RecommendationOut.model_validate(rec)
