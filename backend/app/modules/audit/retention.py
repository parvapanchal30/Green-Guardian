"""Audit retention.

The audit table is append-only. Retention is the one controlled exception: records older than the configured period
may be purged, nothing else may ever be removed.

Layers (each independently refuses a bad purge):
  1. Settings: AUDIT_RETENTION_DAYS must be 0 (keep forever) or >= MIN_RETENTION_DAYS.
  2. This module: refuses a retention shorter than the floor and never deletes a row newer than the cutoff.
  3. PostgreSQL trigger `gg_audit_guard`: a DELETE is allowed only inside a transaction that set `gg.audit_purge = on`
     AND only for rows older than 30 days (a hard floor in the database, independent of this code). UPDATE is never
     allowed. A bug elsewhere in the application therefore cannot delete recent history.
The purge itself is recorded as an `audit.purge` event (written after the deletion, so it is never purged by the run
that created it).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow

from . import service
from .models import AuditEvent

MIN_RETENTION_DAYS = 30  # must match the interval in migration 0006's trigger function
BATCH = 5000


@dataclass(frozen=True)
class PurgeResult:
    retention_days: int
    cutoff: datetime | None
    matched: int
    deleted: int
    dry_run: bool


def purge_expired(
    db: Session, retention_days: int, *, now: datetime | None = None, dry_run: bool = False
) -> PurgeResult:
    if retention_days == 0:  # keep forever
        return PurgeResult(0, None, 0, 0, dry_run)
    if retention_days < MIN_RETENTION_DAYS:
        raise ValueError(f"audit retention must be 0 or at least {MIN_RETENTION_DAYS} days, got {retention_days}")
    now = now or utcnow()
    cutoff = now - timedelta(days=retention_days)
    matched = db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.occurred_at < cutoff)) or 0
    if dry_run or matched == 0:
        return PurgeResult(retention_days, cutoff, matched, 0, dry_run)

    is_pg = db.get_bind().dialect.name == "postgresql"
    deleted = 0
    while True:
        if is_pg:  # transaction-local: unset again at commit/rollback
            db.execute(text("SELECT set_config('gg.audit_purge', 'on', true)"))
        ids = db.scalars(select(AuditEvent.id).where(AuditEvent.occurred_at < cutoff).limit(BATCH)).all()
        if not ids:
            break
        # A Core DELETE (not Session.delete), so the ORM immutability guard is not involved; the database guard is.
        db.execute(delete(AuditEvent).where(AuditEvent.id.in_(ids)))
        deleted += len(ids)
        db.commit()
    service.record(
        db,
        action="audit.purge",
        target_type="audit",
        details={"retention_days": retention_days, "cutoff": cutoff.isoformat(), "deleted": deleted},
    )
    db.commit()
    return PurgeResult(retention_days, cutoff, matched, deleted, False)
