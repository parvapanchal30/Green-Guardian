"""Reconciling the object store with the database: find (and, only when told to, remove) orphan evidence blobs.

Why orphans exist. An upload writes the blob first and the database row second, with a compensating delete if the row fails
(`service.upload`). If the process dies between the two, or the compensating delete itself fails, an object remains that no
row points to. Nothing else ever removes it.

What this module does, in the order it does it:

1. LIST the store and classify every object by its key:
   * `unrecognised`: the key does not have the shape the server generates (`{workspace}/{asset}/{evidence}.{ext}`). It is
     reported and NEVER touched: it may belong to another feature or another system sharing the bucket.
   * `referenced`: a database row (soft-deleted rows included) names this key. Soft-deleted evidence keeps its blob by
     design; retention of such blobs is a separate policy decision and nothing here removes them.
   * `too_recent`: unreferenced but younger than the minimum age. It may be an upload in flight.
   * `orphan`: unreferenced and old enough.
2. CHECK the other direction: live rows whose blob is missing (`missing_blobs`). Reported only; it indicates data loss.
3. DELETE (only when `delete=True`) orphans, under conservative rules:
   * dry-run is the default; a minimum age (never below one hour) protects uploads in flight;
   * the reference is re-checked against the database immediately before each deletion, so a row committed after the
     listing wins the race;
   * refuses to delete anything when the database has no evidence rows at all (it is probably the wrong database), or when
     more than `max_orphan_fraction` of the recognised objects look orphaned (something is wrong with the comparison);
   * deletes at most `max_delete` objects per run;
   * each deletion is audited in the owning workspace when that workspace still exists.
Re-running is idempotent. The comparison never reads object contents and never crosses tenants: the workspace in a key is
only used to scope an optional filter and to place the audit event.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import as_utc, utcnow
from app.modules.audit import service as audit
from app.modules.workspaces.models import Workspace

from .models import Evidence
from .storage import ObjectStore, StorageError, StoredObject

log = structlog.get_logger()

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
KEY_SHAPE = re.compile(rf"^(?P<workspace>{_UUID})/(?P<asset>{_UUID})/(?P<evidence>{_UUID})\.(jpg|png|webp)$")

MIN_AGE_FLOOR = timedelta(hours=1)
DEFAULT_MIN_AGE = timedelta(hours=24)
DEFAULT_MAX_DELETE = 100
DEFAULT_MAX_ORPHAN_FRACTION = 0.2
SMALL_RUN = 5  # below this many orphans the fraction brake does not apply (a tiny store would always trip it)
EXAMPLES = 50
BATCH = 500


class RefusedToDelete(Exception):
    """A safety rule stopped the deletion; nothing was deleted."""


@dataclass
class Report:
    delete_requested: bool
    min_age_hours: float
    objects_total: int = 0
    unrecognised: int = 0
    referenced: int = 0
    too_recent: int = 0
    orphans: int = 0
    orphan_bytes: int = 0
    deleted: int = 0
    skipped_now_referenced: int = 0
    missing_blobs: int = 0
    refused: str | None = None
    orphan_examples: list[str] = field(default_factory=list)
    unrecognised_examples: list[str] = field(default_factory=list)
    missing_examples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {**self.__dict__, "dry_run": not self.delete_requested}


def _referenced(db: Session, keys: list[str]) -> set[str]:
    """Keys that an evidence row (live or soft-deleted) points to. The single place that defines 'referenced': any future
    table that stores object keys must be added here, or its blobs would look orphaned."""
    if not keys:
        return set()
    return set(db.scalars(select(Evidence.storage_key).where(Evidence.storage_key.in_(keys))))


def _batches(items: list[StoredObject]):
    for i in range(0, len(items), BATCH):
        yield items[i : i + BATCH]


def reconcile(
    db: Session,
    store: ObjectStore,
    *,
    delete: bool = False,
    min_age: timedelta = DEFAULT_MIN_AGE,
    max_delete: int = DEFAULT_MAX_DELETE,
    max_orphan_fraction: float = DEFAULT_MAX_ORPHAN_FRACTION,
    workspace_id: uuid.UUID | None = None,
    now: datetime | None = None,
    _referenced_fn: Callable[[Session, list[str]], set[str]] = _referenced,
) -> Report:
    if min_age < MIN_AGE_FLOOR:
        raise ValueError("min_age must be at least one hour: a younger unreferenced object may be an upload in flight")
    if max_delete < 1 or not 0 < max_orphan_fraction <= 1:
        raise ValueError("max_delete must be positive and max_orphan_fraction in (0, 1]")
    now = as_utc(now or utcnow())
    report = Report(delete_requested=delete, min_age_hours=min_age.total_seconds() / 3600)
    workspace_filter = str(workspace_id) if workspace_id else None

    objects = list(store.list())
    report.objects_total = len(objects)
    candidates: list[StoredObject] = []
    store_keys = {o.key for o in objects}
    recognised = 0
    for batch in _batches(objects):
        shaped = [o for o in batch if KEY_SHAPE.match(o.key)]
        for o in batch:
            if not KEY_SHAPE.match(o.key):
                report.unrecognised += 1
                if len(report.unrecognised_examples) < EXAMPLES:
                    report.unrecognised_examples.append(o.key)
        in_scope = [o for o in shaped if workspace_filter is None or o.key.startswith(workspace_filter + "/")]
        recognised += len(in_scope)
        referenced = _referenced_fn(db, [o.key for o in in_scope])
        for o in in_scope:
            if o.key in referenced:
                report.referenced += 1
            elif now - as_utc(o.modified) < min_age:
                report.too_recent += 1
            else:
                candidates.append(o)
    report.orphans = len(candidates)
    report.orphan_bytes = sum(o.size_bytes for o in candidates)
    report.orphan_examples = [o.key for o in candidates[:EXAMPLES]]

    # live rows whose blob is gone (reported, never "fixed")
    live = select(Evidence.id, Evidence.storage_key).where(Evidence.deleted_at.is_(None))
    if workspace_id:
        live = live.where(Evidence.workspace_id == workspace_id)
    for row_id, key in db.execute(live.order_by(Evidence.id)):
        if key not in store_keys:
            report.missing_blobs += 1
            if len(report.missing_examples) < EXAMPLES:
                report.missing_examples.append(f"{row_id}:{key}")

    if not delete or not candidates:
        return report

    rows_total = db.scalar(select(func.count()).select_from(Evidence)) or 0
    if rows_total == 0:
        report.refused = (
            "the database has no evidence rows but the store has objects: this is probably the wrong database"
        )
    elif len(candidates) >= SMALL_RUN and len(candidates) / max(recognised, 1) > max_orphan_fraction:
        report.refused = (
            f"{len(candidates)} of {recognised} recognised objects look orphaned (more than {max_orphan_fraction:.0%}): "
            "investigate before deleting; raise --max-orphan-fraction only if this is expected"
        )
    if report.refused:
        log.warning("evidence_reconcile_refused", reason=report.refused)
        raise RefusedToDelete(report.refused)

    for o in sorted(candidates, key=lambda x: x.modified)[:max_delete]:
        # Close the race with an upload that committed after the listing: re-check right before deleting.
        if _referenced_fn(db, [o.key]):
            report.skipped_now_referenced += 1
            continue
        try:
            store.delete(o.key)
        except StorageError as exc:
            log.error("evidence_reconcile_delete_failed", key=o.key, error=str(exc))
            continue
        report.deleted += 1
        _audit_deletion(db, o, now)
    log.info("evidence_reconcile_done", deleted=report.deleted, orphans=report.orphans)
    return report


def _audit_deletion(db: Session, o: StoredObject, now: datetime) -> None:
    ws_id = uuid.UUID(KEY_SHAPE.match(o.key).group("workspace"))  # type: ignore[union-attr]  # keys here are shaped
    if db.get(Workspace, ws_id) is None:  # the workspace is gone: log only (an audit row needs a workspace)
        log.info("evidence_orphan_purged_no_workspace", key=o.key)
        return
    audit.record(
        db,
        action="evidence.orphan_blob.purged",
        workspace_id=ws_id,
        target_type="storage_object",
        details={
            "key": o.key,
            "size_bytes": o.size_bytes,
            "age_hours": round((now - as_utc(o.modified)).total_seconds() / 3600, 1),
        },
    )
    db.commit()
