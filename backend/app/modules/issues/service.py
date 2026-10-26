from __future__ import annotations

import uuid

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import Conflict, NotFound, Unprocessable
from app.core.pagination import Page, PageParams
from app.core.timeutil import utcnow
from app.modules.actions import service as actions
from app.modules.actions import verification
from app.modules.assets.models import BiologicalAsset
from app.modules.assets.service import get_asset
from app.modules.assets.state import refresh_counts
from app.modules.audit import service as audit
from app.modules.intelligence.models import Outcome
from app.modules.intelligence.outcomes import record_outcome
from app.modules.locations.service import get_location
from app.modules.observations.models import Observation
from app.modules.observations.schemas import ObservationOut
from app.modules.tasks.mapping import load_task_outs
from app.modules.tasks.models import OPEN_TASK_STATUSES, Task, TaskStatus, TaskStatusHistory
from app.modules.workspaces.keys import next_key
from app.modules.workspaces.members import ensure_member

from .models import (
    Issue,
    IssueCategory,
    IssueObservation,
    IssueSource,
    IssueStatusHistory,
    ResolutionOutcome,
    Severity,
)
from .schemas import (
    HistoryOut,
    IssueCreate,
    IssueDetail,
    IssueOut,
    IssueTransition,
    IssueUpdate,
    WorkflowOut,
)
from .workflows import WONT_FIX, WORKFLOWS, Workflow, workflow_for

# "Most severe first" order for the issues list (ADR-073)
SEVERITY_RANK = {Severity.CRITICAL.value: 0, Severity.HIGH.value: 1, Severity.MEDIUM.value: 2, Severity.LOW.value: 3}


def _workflow(issue: Issue) -> Workflow:
    return WORKFLOWS[issue.workflow_key]


def get_issue(db: Session, ctx: WorkspaceContext, issue_id: uuid.UUID, *, lock: bool = False) -> Issue:
    q = select(Issue).where(Issue.id == issue_id, Issue.workspace_id == ctx.workspace_id)
    if lock:
        q = q.with_for_update()  # serialise concurrent transitions of the same issue
    issue = db.scalar(q)
    if issue is None:
        raise NotFound("Issue not found", code="issue_not_found")
    return issue


def _out(issue: Issue, asset_label: str | None) -> IssueOut:
    return IssueOut(
        id=issue.id,
        key=issue.key,
        title=issue.title,
        description=issue.description,
        category=IssueCategory(issue.category),
        severity=Severity(issue.severity),
        workflow_key=issue.workflow_key,
        state=issue.state,
        is_open=issue.resolved_at is None,
        asset_id=issue.asset_id,
        asset_label=asset_label,
        location_id=issue.location_id,
        assignee_id=issue.assignee_id,
        reporter_id=issue.reporter_id,
        source=IssueSource(issue.source),
        origin_observation_id=issue.origin_observation_id,
        recommendation_id=issue.recommendation_id,
        opened_at=issue.opened_at,
        updated_at=issue.updated_at,
        resolved_at=issue.resolved_at,
        resolution_outcome=ResolutionOutcome(issue.resolution_outcome) if issue.resolution_outcome else None,
        resolution_notes=issue.resolution_notes,
        resolved_by=issue.resolved_by,
        version=issue.version,
    )


def _asset_label(db: Session, issue: Issue) -> str | None:
    return (
        db.scalar(select(BiologicalAsset.label).where(BiologicalAsset.id == issue.asset_id)) if issue.asset_id else None
    )


def detail(db: Session, ctx: WorkspaceContext, issue: Issue) -> IssueDetail:
    wf = _workflow(issue)
    history = db.scalars(
        select(IssueStatusHistory)
        .where(IssueStatusHistory.workspace_id == ctx.workspace_id, IssueStatusHistory.issue_id == issue.id)
        .order_by(IssueStatusHistory.at, IssueStatusHistory.id)
    ).all()
    evidence = db.scalars(
        select(Observation)
        .join(
            IssueObservation,
            (IssueObservation.workspace_id == Observation.workspace_id)
            & (IssueObservation.observation_id == Observation.id),
        )
        .where(IssueObservation.workspace_id == ctx.workspace_id, IssueObservation.issue_id == issue.id)
        .order_by(Observation.observed_at)
    ).all()
    tasks = db.scalars(
        select(Task)
        .where(Task.workspace_id == ctx.workspace_id, Task.issue_id == issue.id)
        .order_by(Task.created_at, Task.id)
    ).all()
    base = _out(issue, _asset_label(db, issue))
    return IssueDetail(
        **base.model_dump(),
        history=[
            HistoryOut(from_state=h.from_state, to_state=h.to_state, actor_id=h.actor_id, note=h.note, at=h.at)
            for h in history
        ],
        evidence=[ObservationOut.model_validate(o) for o in evidence],
        tasks=load_task_outs(db, ctx.workspace_id, list(tasks)),
        actions=actions.for_issue(db, ctx, issue.id),
        verification=verification.compute(db, issue),
        allowed_transitions=list(wf.allowed(issue.state)),
    )


def _history(
    db: Session, ctx: WorkspaceContext, issue: Issue, from_state: str | None, to_state: str, note: str | None
) -> None:
    db.add(
        IssueStatusHistory(
            workspace_id=ctx.workspace_id,
            issue_id=issue.id,
            from_state=from_state,
            to_state=to_state,
            actor_id=ctx.user.id,
            note=note,
        )
    )


def _link_evidence(db: Session, ctx: WorkspaceContext, issue: Issue, observation_id: uuid.UUID) -> None:
    exists = db.scalar(
        select(IssueObservation.issue_id).where(
            IssueObservation.issue_id == issue.id, IssueObservation.observation_id == observation_id
        )
    )
    if not exists:
        db.add(
            IssueObservation(
                issue_id=issue.id, observation_id=observation_id, workspace_id=ctx.workspace_id, added_by=ctx.user.id
            )
        )


def create_issue_entity(
    db: Session,
    ctx: WorkspaceContext,
    data: IssueCreate,
    *,
    source: IssueSource | None = None,
    recommendation_id: uuid.UUID | None = None,
) -> Issue:
    """Create an issue (flush, no commit). Used by the API and by accepting a recommendation."""
    asset_id, location_id = data.asset_id, data.location_id
    obs: Observation | None = None
    if data.observation_id:
        obs = db.scalar(
            select(Observation).where(
                Observation.id == data.observation_id, Observation.workspace_id == ctx.workspace_id
            )
        )
        if obs is None:
            raise NotFound("Observation not found", code="observation_not_found")
        if asset_id and obs.asset_id and obs.asset_id != asset_id:
            raise Unprocessable("observation belongs to a different asset", code="observation_asset_mismatch")
        asset_id = asset_id or obs.asset_id
        location_id = location_id or obs.location_id
    if asset_id:
        get_asset(db, ctx, asset_id)
    if location_id:
        get_location(db, ctx, location_id)
    ensure_member(db, ctx, data.assignee_id)

    wf = workflow_for(data.category, ctx.workspace.mode)
    issue = Issue(
        workspace_id=ctx.workspace_id,
        key=next_key(db, ctx.workspace_id, "issue", "GG"),
        title=data.title,
        description=data.description,
        category=data.category.value,
        severity=data.severity.value,
        workflow_key=wf.key,
        state=wf.initial,
        asset_id=asset_id,
        location_id=location_id,
        assignee_id=data.assignee_id,
        reporter_id=ctx.user.id,
        source=(source or (IssueSource.OBSERVATION if obs else IssueSource.MANUAL)).value,
        origin_observation_id=obs.id if obs else None,
        recommendation_id=recommendation_id,
        opened_at=utcnow(),
    )
    db.add(issue)
    db.flush()
    _history(db, ctx, issue, None, wf.initial, "Issue opened")
    if obs:
        _link_evidence(db, ctx, issue, obs.id)
    if asset_id:
        refresh_counts(db, ctx.workspace_id, asset_id)
    return issue


def create_issue(db: Session, ctx: WorkspaceContext, data: IssueCreate) -> IssueDetail:
    issue = create_issue_entity(db, ctx, data)
    audit.record_ctx(
        db,
        ctx,
        "issue.create",
        target_type="issue",
        target_id=issue.id,
        details={"key": issue.key, "severity": issue.severity, "category": issue.category, "asset_id": issue.asset_id},
    )
    db.commit()
    return detail(db, ctx, issue)


def list_issues(
    db: Session,
    ctx: WorkspaceContext,
    page: PageParams,
    *,
    state: str | None = None,
    is_open: bool | None = None,
    severity: Severity | None = None,
    category: IssueCategory | None = None,
    assignee: str | None = None,
    asset_id: uuid.UUID | None = None,
    q: str | None = None,
    waiting: bool | None = None,
    sort: str = "recent",
) -> Page[IssueOut]:
    stmt = (
        select(Issue, BiologicalAsset.label)
        .outerjoin(BiologicalAsset, BiologicalAsset.id == Issue.asset_id)
        .where(Issue.workspace_id == ctx.workspace_id)
    )
    if state:
        stmt = stmt.where(Issue.state == state)
    if is_open is True:
        stmt = stmt.where(Issue.resolved_at.is_(None))
    if is_open is False:
        stmt = stmt.where(Issue.resolved_at.is_not(None))
    if severity:
        stmt = stmt.where(Issue.severity == severity.value)
    if category:
        stmt = stmt.where(Issue.category == category.value)
    if assignee == "me":
        stmt = stmt.where(Issue.assignee_id == ctx.user.id)
    elif assignee:
        try:
            stmt = stmt.where(Issue.assignee_id == uuid.UUID(assignee))
        except ValueError as e:
            raise Unprocessable("assignee must be 'me' or a user id", code="bad_assignee") from e
    if asset_id:
        stmt = stmt.where(Issue.asset_id == asset_id)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(Issue.title).like(like), func.lower(Issue.key).like(like)))
    if waiting is not None:
        # each workflow names its own waiting states; an issue waits when its state is one of its workflow's
        pairs = [and_(Issue.workflow_key == w.key, Issue.state.in_(w.waiting)) for w in WORKFLOWS.values() if w.waiting]
        stmt = stmt.where(or_(*pairs) if waiting else ~or_(*pairs))
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    order = [Issue.opened_at.desc(), Issue.id]
    if sort == "severity":
        rank = case(SEVERITY_RANK, value=Issue.severity, else_=len(SEVERITY_RANK))
        order = [rank, *order]
    rows = db.execute(stmt.order_by(*order).limit(page.limit).offset(page.offset)).all()
    return Page(items=[_out(i, label) for i, label in rows], total=total, limit=page.limit, offset=page.offset)


def get_detail(db: Session, ctx: WorkspaceContext, issue_id: uuid.UUID) -> IssueDetail:
    return detail(db, ctx, get_issue(db, ctx, issue_id))


def update_issue(db: Session, ctx: WorkspaceContext, issue_id: uuid.UUID, data: IssueUpdate) -> IssueDetail:
    issue = get_issue(db, ctx, issue_id, lock=True)
    sent = data.model_fields_set
    changes: list[str] = []
    if "title" in sent and data.title and data.title != issue.title:
        changes.append("title changed")
        issue.title = data.title
    if "description" in sent and data.description != issue.description:
        changes.append("description changed")
        issue.description = data.description
    if "severity" in sent and data.severity and data.severity.value != issue.severity:
        changes.append(f"severity {issue.severity} → {data.severity.value}")
        issue.severity = data.severity.value
    if "assignee_id" in sent and data.assignee_id != issue.assignee_id:
        ensure_member(db, ctx, data.assignee_id)
        changes.append("reassigned" if data.assignee_id else "unassigned")
        issue.assignee_id = data.assignee_id
    if changes:
        issue.version += 1
        # Field changes are audited as a history row whose from_state equals to_state.
        _history(db, ctx, issue, issue.state, issue.state, "; ".join(changes))
        audit.record_ctx(
            db,
            ctx,
            "issue.update",
            target_type="issue",
            target_id=issue.id,
            details={"key": issue.key, "changes": changes},
        )
    db.commit()
    return detail(db, ctx, issue)


def _cancel_open_tasks(db: Session, ctx: WorkspaceContext, issue: Issue) -> list[str]:
    tasks = db.scalars(
        select(Task).where(
            Task.workspace_id == ctx.workspace_id,
            Task.issue_id == issue.id,
            Task.status.in_([s.value for s in OPEN_TASK_STATUSES]),
        )
    ).all()
    for t in tasks:
        db.add(
            TaskStatusHistory(
                workspace_id=ctx.workspace_id,
                task_id=t.id,
                from_status=t.status,
                to_status=TaskStatus.CANCELLED.value,
                actor_id=ctx.user.id,
                note=f"Cancelled when {issue.key} was closed",
            )
        )
        t.status = TaskStatus.CANCELLED.value
        t.version += 1
    return [t.key for t in tasks]


def _record_follow_up(db: Session, ctx: WorkspaceContext, issue: Issue, data) -> None:
    """The follow-up observation sent with a resolution: stored like any observation and attached as evidence."""
    from app.modules.observations.models import ObservationKind
    from app.modules.observations.schemas import ObservationCreate
    from app.modules.observations.service import create_observation

    assert issue.asset_id is not None  # checked by the caller
    created = create_observation(
        db,
        ctx,
        ObservationCreate(
            asset_id=issue.asset_id,
            kind=ObservationKind.HEALTH,
            health_score=data.health_score,
            symptoms=data.symptoms,
            notes=data.notes or f"Follow-up recorded when closing {issue.key}",
            attachments=data.attachments,
        ),
        commit=False,
    )
    _link_evidence(db, ctx, issue, created.observation.id)


def transition(db: Session, ctx: WorkspaceContext, issue_id: uuid.UUID, data: IssueTransition) -> IssueDetail:
    issue = get_issue(db, ctx, issue_id, lock=True)
    wf = _workflow(issue)
    wf.check(issue.state, data.to_state)
    now = utcnow()
    from_state, to_state = issue.state, data.to_state
    note = data.note

    if wf.is_terminal(to_state):
        res = data.resolution
        if res is None:
            raise Unprocessable("closing an issue needs a resolution", code="resolution_required")
        if to_state == WONT_FIX:
            if res.outcome != ResolutionOutcome.WONT_FIX:
                raise Unprocessable("closing as won't fix needs outcome 'wont_fix'", code="outcome_mismatch")
            if not (res.notes or "").strip():
                raise Unprocessable("explain why this will not be fixed", code="notes_required")
        elif res.outcome == ResolutionOutcome.WONT_FIX:
            raise Unprocessable("outcome 'wont_fix' only applies to the won't-fix state", code="outcome_mismatch")
        open_keys = [
            k
            for k in db.scalars(
                select(Task.key).where(
                    Task.workspace_id == ctx.workspace_id,
                    Task.issue_id == issue.id,
                    Task.status.in_([s.value for s in OPEN_TASK_STATUSES]),
                )
            )
        ]
        if open_keys and not res.cancel_open_tasks:
            raise Conflict(
                "open tasks must be completed or cancelled first (or pass cancel_open_tasks)",
                code="open_tasks",
                extra={"tasks": open_keys},
            )
        if res.follow_up is not None:
            if issue.asset_id is None:
                raise Unprocessable("this issue has no asset to observe", code="issue_has_no_asset")
            _record_follow_up(db, ctx, issue, res.follow_up)
            now = utcnow()  # the closing time comes after the follow-up, so it falls inside the verified window
        if verification.requires_follow_up(issue, res.outcome.value):
            check = verification.compute(db, issue, until=utcnow())
            if check.status == "awaiting_follow_up":
                raise Conflict(
                    "record an observation of the asset after the last action (or send one as follow_up) before "
                    "closing this issue as fixed or mitigated",
                    code="follow_up_required",
                    extra={"last_action_at": check.last_action_at.isoformat() if check.last_action_at else None},
                )
        if open_keys:
            _cancel_open_tasks(db, ctx, issue)
        issue.resolved_at = now
        issue.resolution_outcome = res.outcome.value
        issue.resolution_notes = res.notes
        issue.resolved_by = ctx.user.id
    elif issue.resolved_at is not None:  # reopening: the resolution is cleared; the history keeps what happened
        issue.resolved_at = None
        issue.resolution_outcome = None
        issue.resolution_notes = None
        issue.resolved_by = None
        note = note or "Reopened"

    issue.state = to_state
    issue.version += 1
    _history(db, ctx, issue, from_state, to_state, note or (data.resolution.notes if data.resolution else None))
    if issue.asset_id:
        refresh_counts(
            db,
            ctx.workspace_id,
            issue.asset_id,
            resolved_at=now if wf.is_terminal(to_state) and to_state in wf.success else None,
        )
    if wf.is_terminal(to_state):  # follow-up for the suggestion behind it
        record_outcome(
            db,
            ctx.workspace_id,
            issue.recommendation_id,
            Outcome.ISSUE_RESOLVED if to_state in wf.success else Outcome.ISSUE_CLOSED,
            detail=f"issue {issue.key} {to_state}",
            at=now,
        )
    audit.record_ctx(
        db,
        ctx,
        "issue.transition",
        target_type="issue",
        target_id=issue.id,
        details={
            "key": issue.key,
            "from": from_state,
            "to": to_state,
            "resolution": data.resolution.outcome.value if data.resolution else None,
            "follow_up_observation": bool(data.resolution and data.resolution.follow_up),
        },
    )
    db.commit()
    return detail(db, ctx, issue)


def add_evidence(db: Session, ctx: WorkspaceContext, issue_id: uuid.UUID, observation_id: uuid.UUID) -> IssueDetail:
    issue = get_issue(db, ctx, issue_id)
    obs = db.scalar(
        select(Observation).where(Observation.id == observation_id, Observation.workspace_id == ctx.workspace_id)
    )
    if obs is None:
        raise NotFound("Observation not found", code="observation_not_found")
    if issue.asset_id and obs.asset_id != issue.asset_id:
        raise Unprocessable("observation belongs to a different asset", code="observation_asset_mismatch")
    _link_evidence(db, ctx, issue, obs.id)
    audit.record_ctx(
        db,
        ctx,
        "issue.evidence_add",
        target_type="issue",
        target_id=issue.id,
        details={"key": issue.key, "observation_id": obs.id},
    )
    db.commit()
    return detail(db, ctx, issue)


def workflows() -> list[WorkflowOut]:
    return [
        WorkflowOut(
            key=w.key,
            label=w.label,
            states=list(w.states),
            initial=w.initial,
            terminal=sorted(w.terminal),
            transitions={k: list(v) for k, v in w.transitions.items()},
        )
        for w in WORKFLOWS.values()
    ]
