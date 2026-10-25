"""Recording and reading the work done to assets (ADR-059)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.core.timeutil import as_utc, utcnow
from app.modules.assets import lifecycle as lc
from app.modules.assets.models import BiologicalAsset
from app.modules.audit import service as audit
from app.modules.issues.models import Issue
from app.modules.tasks.models import Task
from app.modules.workspaces.members import ensure_member
from app.modules.workspaces.models import Role

from .models import ActionRecord
from .schemas import ActionCorrect, ActionCreate, ActionDone, ActionOut, AssetActions

FUTURE_TOLERANCE = timedelta(minutes=5)
HISTORY_LIMIT = 500
KIND_LABELS = {
    "treat": "treatment",
    "water": "watering",
    "fertilize": "fertilising",
    "prune": "pruning",
    "pest_control": "pest control",
    "weed": "weeding",
    "mulch": "mulching",
    "replant": "replanting",
    "other": "work",
}


def _when(asset: BiologicalAsset, value: datetime | None, default: datetime) -> datetime:
    performed_at = as_utc(value) if value else default
    if performed_at > utcnow() + FUTURE_TOLERANCE:
        raise Unprocessable("performed_at cannot be in the future", code="performed_in_future")
    if asset.planted_at is not None:
        planted = datetime.combine(asset.planted_at, datetime.min.time(), tzinfo=UTC)
        if performed_at < planted:
            raise Unprocessable(
                f"performed_at cannot be before the planting date ({asset.planted_at.isoformat()})",
                code="performed_before_planting",
            )
    return performed_at


def _clean(text: str | None) -> str | None:
    return (text or "").strip() or None


def _check_asset(asset: BiologicalAsset) -> None:
    if lc.is_exit(asset.current_stage):
        raise Conflict(
            f"This asset has left the lifecycle ({asset.current_stage}); no work can be recorded on it",
            code="asset_exited",
        )


def record_entity(
    db: Session,
    ctx: WorkspaceContext,
    asset: BiologicalAsset,
    data: ActionDone,
    *,
    issue: Issue | None = None,
    task: Task | None = None,
    performed_at: datetime | None = None,
    performed_by: uuid.UUID | None = None,
    follow_up_task: Task | None = None,
) -> ActionRecord:
    """Insert one action (flush, no commit) and audit it. The caller has checked the asset, issue and task."""
    _check_asset(asset)
    rec = ActionRecord(
        workspace_id=ctx.workspace_id,
        asset_id=asset.id,
        issue_id=issue.id if issue else (task.issue_id if task else None),
        task_id=task.id if task else None,
        kind=data.kind,
        product=_clean(data.product),
        quantity=data.quantity,
        unit=data.unit,
        performed_at=performed_at or utcnow(),
        performed_by=performed_by or ctx.user.id,
        note=_clean(data.note),
        follow_up_task_id=follow_up_task.id if follow_up_task else None,
        recorded_by=ctx.user.id,
    )
    db.add(rec)
    db.flush()
    audit.record_ctx(
        db,
        ctx,
        "action.record",
        target_type="action",
        target_id=rec.id,
        details={
            "asset_id": asset.id,
            "kind": rec.kind,
            "issue_id": rec.issue_id,
            "task_id": rec.task_id,
            "follow_up_task_id": rec.follow_up_task_id,
        },
    )
    return rec


def _open_issue_of(db: Session, ctx: WorkspaceContext, asset: BiologicalAsset, issue_id: uuid.UUID) -> Issue:
    issue = db.scalar(select(Issue).where(Issue.workspace_id == ctx.workspace_id, Issue.id == issue_id))
    if issue is None:
        raise NotFound("Issue not found", code="issue_not_found")
    if issue.asset_id != asset.id:
        raise Unprocessable("the issue belongs to a different asset", code="issue_asset_mismatch")
    if issue.resolved_at is not None:
        raise Conflict("this issue is closed; reopen it before recording work on it", code="issue_closed")
    return issue


def record(db: Session, ctx: WorkspaceContext, asset: BiologicalAsset, data: ActionCreate) -> AssetActions:
    _check_asset(asset)
    issue = _open_issue_of(db, ctx, asset, data.issue_id) if data.issue_id else None
    performer = data.performed_by or ctx.user.id
    if performer != ctx.user.id:
        if not ctx.has_role(Role.MANAGER):
            raise Forbidden("only a manager can record work done by someone else", code="insufficient_role")
        ensure_member(db, ctx, performer)
    performed_at = _when(asset, data.performed_at, utcnow())

    follow_up = None
    if data.follow_up_days:
        from app.modules.tasks.models import TaskType
        from app.modules.tasks.schemas import TaskCreate
        from app.modules.tasks.service import create_task_entity

        follow_up = create_task_entity(
            db,
            ctx,
            TaskCreate(
                title=f"Check the result of the {KIND_LABELS[data.kind]} on {asset.label}"[:300],
                type=TaskType.INSPECT,
                description="Look at the asset and record an observation: this is how the work is verified.",
                issue_id=issue.id if issue else None,
                asset_id=asset.id,
                assignee_id=performer,
                due_at=max(performed_at, utcnow()) + timedelta(days=data.follow_up_days),
            ),
        )
    record_entity(
        db, ctx, asset, data, issue=issue, performed_at=performed_at, performed_by=performer, follow_up_task=follow_up
    )
    db.commit()
    return view(db, ctx, asset)


def correct(
    db: Session, ctx: WorkspaceContext, asset: BiologicalAsset, action_id: uuid.UUID, data: ActionCorrect
) -> AssetActions:
    target = db.scalar(
        select(ActionRecord)
        .where(
            ActionRecord.workspace_id == ctx.workspace_id,
            ActionRecord.asset_id == asset.id,
            ActionRecord.id == action_id,
        )
        .with_for_update()  # two simultaneous corrections of one record: the second must see the first
    )
    if target is None:
        raise NotFound("Action not found", code="action_not_found")
    already = db.scalar(
        select(func.count())
        .select_from(ActionRecord)
        .where(ActionRecord.workspace_id == ctx.workspace_id, ActionRecord.supersedes_id == target.id)
    )
    if already:
        raise Conflict(
            "This record was already corrected; correct the latest version instead", code="action_already_corrected"
        )
    note = data.note.strip()
    if len(note) < 10:
        raise Unprocessable("A correction needs a written reason of at least 10 characters", code="reason_required")
    rec = ActionRecord(
        workspace_id=ctx.workspace_id,
        asset_id=asset.id,
        issue_id=target.issue_id,
        task_id=target.task_id,
        kind=data.kind,
        product=_clean(data.product),
        quantity=data.quantity,
        unit=data.unit,
        performed_at=_when(asset, data.performed_at, as_utc(target.performed_at)),
        performed_by=target.performed_by,
        note=note,
        supersedes_id=target.id,
        withdrawn=data.withdrawn,
        recorded_by=ctx.user.id,
    )
    db.add(rec)
    try:
        db.flush()
    except IntegrityError as exc:  # the database's one-correction-per-record index won a race
        db.rollback()
        raise Conflict("This record was already corrected", code="action_already_corrected") from exc
    audit.record_ctx(
        db,
        ctx,
        "action.correct",
        target_type="action",
        target_id=rec.id,
        details={"asset_id": asset.id, "supersedes": target.id, "kind": rec.kind, "withdrawn": rec.withdrawn},
    )
    db.commit()
    return view(db, ctx, asset)


def _outs(db: Session, ctx: WorkspaceContext, rows: list[ActionRecord]) -> list[ActionOut]:
    ids = {r.id for r in rows}
    replaced_by = (
        {
            old: new
            for old, new in db.execute(
                select(ActionRecord.supersedes_id, ActionRecord.id).where(
                    ActionRecord.workspace_id == ctx.workspace_id, ActionRecord.supersedes_id.in_(ids)
                )
            )
        }
        if ids
        else {}
    )
    issue_ids = {r.issue_id for r in rows if r.issue_id}
    task_ids = {t for r in rows for t in (r.task_id, r.follow_up_task_id) if t}
    issue_keys: dict = {}
    if issue_ids:
        q = select(Issue.id, Issue.key).where(Issue.workspace_id == ctx.workspace_id, Issue.id.in_(issue_ids))
        issue_keys = {i: k for i, k in db.execute(q)}
    task_keys: dict = {}
    if task_ids:
        q = select(Task.id, Task.key).where(Task.workspace_id == ctx.workspace_id, Task.id.in_(task_ids))
        task_keys = {i: k for i, k in db.execute(q)}
    return [
        ActionOut(
            id=r.id,
            asset_id=r.asset_id,
            issue_id=r.issue_id,
            issue_key=issue_keys.get(r.issue_id) if r.issue_id else None,
            task_id=r.task_id,
            task_key=task_keys.get(r.task_id) if r.task_id else None,
            kind=r.kind,
            product=r.product,
            quantity=r.quantity,
            unit=r.unit,
            performed_at=as_utc(r.performed_at),
            performed_by=r.performed_by,
            note=r.note,
            follow_up_task_id=r.follow_up_task_id,
            follow_up_task_key=task_keys.get(r.follow_up_task_id) if r.follow_up_task_id else None,
            supersedes_id=r.supersedes_id,
            superseded_by=replaced_by.get(r.id),
            effective=r.id not in replaced_by,
            withdrawn=r.withdrawn,
            recorded_by=r.recorded_by,
            recorded_at=as_utc(r.created_at),
        )
        for r in rows
    ]


def view(db: Session, ctx: WorkspaceContext, asset: BiologicalAsset) -> AssetActions:
    rows = db.scalars(
        select(ActionRecord)
        .where(ActionRecord.workspace_id == ctx.workspace_id, ActionRecord.asset_id == asset.id)
        .order_by(ActionRecord.performed_at.desc(), ActionRecord.created_at.desc(), ActionRecord.id.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    return AssetActions(asset_id=asset.id, history=_outs(db, ctx, list(rows)))


def for_issue(db: Session, ctx: WorkspaceContext, issue_id: uuid.UUID) -> list[ActionOut]:
    """Every action recorded on an issue, corrections included, oldest first."""
    rows = db.scalars(
        select(ActionRecord)
        .where(ActionRecord.workspace_id == ctx.workspace_id, ActionRecord.issue_id == issue_id)
        .order_by(ActionRecord.performed_at, ActionRecord.created_at, ActionRecord.id)
        .limit(HISTORY_LIMIT)
    ).all()
    return _outs(db, ctx, list(rows))
