"""Recurring inspections (ADR-062): schedules, and the pass that turns due schedules into tasks."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import Conflict, NotFound, Unprocessable
from app.core.timeutil import as_utc, utcnow
from app.modules.assets import lifecycle as lc
from app.modules.assets.models import BiologicalAsset
from app.modules.assets.state import refresh_counts
from app.modules.audit import service as audit
from app.modules.locations.models import Location
from app.modules.tasks.models import OPEN_TASK_STATUSES, Task, TaskSource, TaskStatus, TaskStatusHistory
from app.modules.workspaces.keys import next_key
from app.modules.workspaces.members import ensure_member

from .models import InspectionSchedule, ScheduleOccurrence
from .schemas import GenerateResult, OccurrenceOut, ScheduleCreate, ScheduleDetail, ScheduleOut, ScheduleUpdate

log = structlog.get_logger(__name__)
MAX_PAST = timedelta(days=366)  # a first due date further back is almost certainly a typo
HISTORY = 50
BATCH = 500  # schedules handled per pass; the next pass picks up the rest


# ------------------------------------------------------------------ reading


def _get(db: Session, ctx: WorkspaceContext, schedule_id: uuid.UUID, *, lock: bool = False) -> InspectionSchedule:
    q = select(InspectionSchedule).where(
        InspectionSchedule.workspace_id == ctx.workspace_id, InspectionSchedule.id == schedule_id
    )
    s = db.scalar(q.with_for_update() if lock else q)
    if s is None:
        raise NotFound("Schedule not found", code="schedule_not_found")
    return s


def _outs(db: Session, ctx: WorkspaceContext, rows: list[InspectionSchedule]) -> list[ScheduleOut]:
    asset_ids = {r.asset_id for r in rows if r.asset_id}
    location_ids = {r.location_id for r in rows if r.location_id}
    labels: dict = {}
    names: dict = {}
    if asset_ids:
        q = select(BiologicalAsset.id, BiologicalAsset.label).where(
            BiologicalAsset.workspace_id == ctx.workspace_id, BiologicalAsset.id.in_(asset_ids)
        )
        labels = {i: label for i, label in db.execute(q)}
    if location_ids:
        q = select(Location.id, Location.name).where(
            Location.workspace_id == ctx.workspace_id, Location.id.in_(location_ids)
        )
        names = {i: name for i, name in db.execute(q)}
    return [
        ScheduleOut(
            id=r.id,
            asset_id=r.asset_id,
            asset_label=labels.get(r.asset_id) if r.asset_id else None,
            location_id=r.location_id,
            location_name=names.get(r.location_id) if r.location_id else None,
            title=r.title,
            task_type=r.task_type,
            interval_days=r.interval_days,
            lead_days=r.lead_days,
            next_due_at=r.next_due_at,
            assignee_id=r.assignee_id,
            priority=r.priority,
            active=r.active,
            created_by=r.created_by,
            created_at=r.created_at,
            updated_at=r.updated_at,
            version=r.version,
        )
        for r in rows
    ]


def list_schedules(
    db: Session,
    ctx: WorkspaceContext,
    *,
    asset_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    active: bool | None = None,
) -> list[ScheduleOut]:
    q = select(InspectionSchedule).where(InspectionSchedule.workspace_id == ctx.workspace_id)
    if asset_id:
        q = q.where(InspectionSchedule.asset_id == asset_id)
    if location_id:
        q = q.where(InspectionSchedule.location_id == location_id)
    if active is not None:
        q = q.where(InspectionSchedule.active.is_(active))
    rows = db.scalars(q.order_by(InspectionSchedule.active.desc(), InspectionSchedule.next_due_at).limit(500)).all()
    return _outs(db, ctx, list(rows))


def detail(db: Session, ctx: WorkspaceContext, s: InspectionSchedule) -> ScheduleDetail:
    rows = db.execute(
        select(ScheduleOccurrence, Task.key, Task.status)
        .outerjoin(
            Task, (Task.workspace_id == ScheduleOccurrence.workspace_id) & (Task.id == ScheduleOccurrence.task_id)
        )
        .where(ScheduleOccurrence.workspace_id == ctx.workspace_id, ScheduleOccurrence.schedule_id == s.id)
        .order_by(ScheduleOccurrence.due_at.desc())
        .limit(HISTORY)
    ).all()
    occurrences = [
        OccurrenceOut(
            due_at=o.due_at,
            outcome=o.outcome,
            task_id=o.task_id,
            task_key=key,
            task_status=status,
            missed=o.missed,
            created_at=o.created_at,
        )
        for o, key, status in rows
    ]
    return ScheduleDetail(**_outs(db, ctx, [s])[0].model_dump(), occurrences=occurrences)


def get_detail(db: Session, ctx: WorkspaceContext, schedule_id: uuid.UUID) -> ScheduleDetail:
    return detail(db, ctx, _get(db, ctx, schedule_id))


# ------------------------------------------------------------------ changing


def _check_due(value: datetime) -> datetime:
    when = as_utc(value)
    if when < utcnow() - MAX_PAST:
        raise Unprocessable("the due date is more than a year in the past", code="due_too_old")
    return when


def create(db: Session, ctx: WorkspaceContext, data: ScheduleCreate) -> ScheduleDetail:
    subject = ""
    if data.asset_id:
        asset = db.scalar(
            select(BiologicalAsset).where(
                BiologicalAsset.workspace_id == ctx.workspace_id, BiologicalAsset.id == data.asset_id
            )
        )
        if asset is None:
            raise NotFound("Asset not found", code="asset_not_found")
        if asset.archived_at is not None or lc.is_exit(asset.current_stage):
            raise Conflict(
                "this asset is archived or has left the lifecycle; it needs no inspections", code="asset_inactive"
            )
        subject = asset.label
    if data.location_id:
        loc = db.scalar(
            select(Location).where(Location.workspace_id == ctx.workspace_id, Location.id == data.location_id)
        )
        if loc is None:
            raise NotFound("Location not found", code="location_not_found")
        subject = loc.name
    ensure_member(db, ctx, data.assignee_id)
    verb = "Inspect" if data.task_type == "inspect" else "Monitor"
    s = InspectionSchedule(
        workspace_id=ctx.workspace_id,
        asset_id=data.asset_id,
        location_id=data.location_id,
        title=(data.title or f"{verb} {subject}").strip()[:200],
        task_type=data.task_type,
        interval_days=data.interval_days,
        lead_days=data.lead_days,
        next_due_at=_check_due(data.first_due_at) if data.first_due_at else utcnow(),
        assignee_id=data.assignee_id,
        priority=data.priority,
        active=True,
        created_by=ctx.user.id,
    )
    db.add(s)
    db.flush()
    audit.record_ctx(
        db,
        ctx,
        "schedule.create",
        target_type="schedule",
        target_id=s.id,
        details={"asset_id": s.asset_id, "location_id": s.location_id, "interval_days": s.interval_days},
    )
    db.commit()
    generate(db, workspace_id=ctx.workspace_id, schedule_id=s.id)  # the first one may already be due
    return detail(db, ctx, _get(db, ctx, s.id))


def update(db: Session, ctx: WorkspaceContext, schedule_id: uuid.UUID, data: ScheduleUpdate) -> ScheduleDetail:
    s = _get(db, ctx, schedule_id, lock=True)
    sent = data.model_fields_set
    changes: dict[str, list] = {}

    def change(field: str, value) -> None:
        if getattr(s, field) != value:
            changes[field] = [getattr(s, field), value]
            setattr(s, field, value)

    if "title" in sent and data.title:
        change("title", data.title.strip())
    if "interval_days" in sent and data.interval_days is not None:
        change("interval_days", data.interval_days)
    if "lead_days" in sent and data.lead_days is not None:
        change("lead_days", data.lead_days)
    if s.lead_days >= s.interval_days:
        raise Unprocessable("lead_days must be smaller than interval_days", code="lead_too_long")
    if "next_due_at" in sent and data.next_due_at is not None:
        change("next_due_at", _check_due(data.next_due_at))
    if "assignee_id" in sent:
        ensure_member(db, ctx, data.assignee_id)
        change("assignee_id", data.assignee_id)
    if "priority" in sent and data.priority:
        change("priority", data.priority)
    if "active" in sent and data.active is not None:
        if data.active and s.asset_id:
            asset = db.get(BiologicalAsset, s.asset_id)
            if asset is None or asset.archived_at is not None or lc.is_exit(asset.current_stage):
                raise Conflict("this asset is archived or has left the lifecycle", code="asset_inactive")
        change("active", data.active)
    if changes:
        s.version += 1
        audit.record_ctx(
            db,
            ctx,
            "schedule.update",
            target_type="schedule",
            target_id=s.id,
            details={k: [str(v) for v in pair] for k, pair in changes.items()},
        )
    db.commit()
    if changes:
        generate(db, workspace_id=ctx.workspace_id, schedule_id=s.id)
    return detail(db, ctx, _get(db, ctx, s.id))


# ------------------------------------------------------------------ generating tasks


def _open_task_of(db: Session, s: InspectionSchedule) -> Task | None:
    """The task this schedule created that is still open, if any (a new one would only pile up next to it)."""
    return db.scalar(
        select(Task)
        .join(
            ScheduleOccurrence,
            (ScheduleOccurrence.workspace_id == Task.workspace_id) & (ScheduleOccurrence.task_id == Task.id),
        )
        .where(
            ScheduleOccurrence.workspace_id == s.workspace_id,
            ScheduleOccurrence.schedule_id == s.id,
            Task.status.in_([st.value for st in OPEN_TASK_STATUSES]),
        )
        .limit(1)
    )


def _inactive_asset(db: Session, s: InspectionSchedule) -> bool:
    if s.asset_id is None:
        return False
    asset = db.scalar(
        select(BiologicalAsset).where(BiologicalAsset.workspace_id == s.workspace_id, BiologicalAsset.id == s.asset_id)
    )
    return asset is None or asset.archived_at is not None or lc.is_exit(asset.current_stage)


def _create_task(db: Session, s: InspectionSchedule, due: datetime) -> Task:
    task = Task(
        workspace_id=s.workspace_id,
        key=next_key(db, s.workspace_id, "task", "T"),
        type=s.task_type,
        title=s.title,
        description=f"Created by a recurring schedule: every {s.interval_days} day(s).",
        asset_id=s.asset_id,
        location_id=s.location_id,
        assignee_id=s.assignee_id,
        created_by=s.created_by,
        priority=s.priority,
        status=TaskStatus.TODO.value,
        source=TaskSource.SCHEDULE.value,
        due_at=due,
    )
    db.add(task)
    db.flush()
    db.add(
        TaskStatusHistory(
            workspace_id=s.workspace_id,
            task_id=task.id,
            from_status=None,
            to_status=task.status,
            actor_id=None,  # the system, on the schedule's behalf
            note=f"Created by the schedule '{s.title}'",
        )
    )
    if s.asset_id:
        refresh_counts(db, s.workspace_id, s.asset_id)
    return task


def _one(db: Session, schedule_id: uuid.UUID, now: datetime, result: GenerateResult) -> None:
    s = db.scalar(
        select(InspectionSchedule).where(InspectionSchedule.id == schedule_id).with_for_update(skip_locked=True)
    )
    if s is None or not s.active or as_utc(s.next_due_at) - timedelta(days=s.lead_days) > now:
        return  # another worker took it, or it changed since it was listed
    step = timedelta(days=s.interval_days)
    due, missed = as_utc(s.next_due_at), 0
    while due + step - timedelta(days=s.lead_days) <= now:  # nothing generated these in time: catch up to the latest
        due += step
        missed += 1
    result.due += 1
    task = None
    if _inactive_asset(db, s):
        outcome = "skipped_inactive_asset"
        s.active = False  # a dead or removed plant needs no more inspections
        result.skipped_inactive_asset += 1
    elif _open_task_of(db, s) is not None:
        outcome = "skipped_open_task"
        result.skipped_open_task += 1
    else:
        task = _create_task(db, s, due)
        outcome = "created"
        result.created += 1
        result.task_keys.append(task.key)
    db.add(
        ScheduleOccurrence(
            workspace_id=s.workspace_id,
            schedule_id=s.id,
            due_at=due,
            outcome=outcome,
            task_id=task.id if task else None,
            missed=missed,
        )
    )
    s.next_due_at = due + step
    s.version += 1
    audit.record(
        db,
        action="schedule.generate",
        workspace_id=s.workspace_id,
        target_type="schedule",
        target_id=s.id,
        details={"due_at": due.isoformat(), "outcome": outcome, "task_id": task.id if task else None, "missed": missed},
    )
    db.flush()


def generate(
    db: Session,
    *,
    now: datetime | None = None,
    workspace_id: uuid.UUID | None = None,
    schedule_id: uuid.UUID | None = None,
) -> GenerateResult:
    """Turn every due schedule (optionally of one workspace, or just one schedule) into its next task. Each schedule is
    its own transaction, so one failure never blocks the others and a crash leaves nothing half-done."""
    now = now or utcnow()
    result = GenerateResult(due=0, created=0, skipped_open_task=0, skipped_inactive_asset=0, task_keys=[])
    q = select(InspectionSchedule.id, InspectionSchedule.next_due_at, InspectionSchedule.lead_days).where(
        InspectionSchedule.active.is_(True), InspectionSchedule.next_due_at <= now + timedelta(days=30)
    )
    if workspace_id:
        q = q.where(InspectionSchedule.workspace_id == workspace_id)
    if schedule_id:
        q = q.where(InspectionSchedule.id == schedule_id)
    candidates = [
        sid
        for sid, due, lead in db.execute(q.order_by(InspectionSchedule.next_due_at).limit(BATCH))
        if as_utc(due) - timedelta(days=lead) <= now
    ]
    for sid in candidates:
        try:
            _one(db, sid, now, result)
            db.commit()
        except IntegrityError:  # another worker generated this due date first (unique schedule + due date)
            db.rollback()
        except Exception:
            db.rollback()
            log.exception("schedule_generate_failed", schedule_id=str(sid))
    return result
