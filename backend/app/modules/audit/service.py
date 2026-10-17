"""Recording and reading audit events.

`record()` only ADDS a row to the caller's session: it commits (or rolls back) together with the change it describes.
Everything passed in `details` is scrubbed: credential-looking keys are dropped, strings are truncated, and the whole
payload is size-capped, so a careless call site cannot leak a secret or bloat the table.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.pagination import Page, PageParams
from app.core.request_context import current_client_ip, current_request_id, current_user_agent
from app.modules.identity.models import User

from .models import AuditEvent
from .schemas import AuditEventOut

if TYPE_CHECKING:  # deps imports identity.service, which records audit events: avoid the import cycle
    from app.core.deps import WorkspaceContext

_SECRET_KEY = re.compile(r"pass(word|wd)?|secret|token|authorization|cookie|api[_-]?key|credential|hash|private", re.I)
MAX_STRING = 300
MAX_DETAILS_BYTES = 4000


def scrub(value: Any, _depth: int = 0) -> Any:
    """JSON-safe copy of `value` with credential-like keys removed and sizes bounded."""
    if _depth > 5:
        return "…"
    if isinstance(value, dict):
        return {str(k)[:64]: scrub(v, _depth + 1) for k, v in value.items() if not _SECRET_KEY.search(str(k))}
    if isinstance(value, (list, tuple, set)):
        return [scrub(v, _depth + 1) for v in list(value)[:50]]
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, (uuid.UUID, datetime)):
        return str(value)
    text = str(value)
    return text if len(text) <= MAX_STRING else text[:MAX_STRING] + "…"


def _bounded(details: dict) -> dict:
    clean = scrub(details)
    if len(json.dumps(clean, default=str)) > MAX_DETAILS_BYTES:
        return {"truncated": True, "keys": sorted(clean)[:20]}
    return clean


def record(
    db: Session,
    *,
    action: str,
    workspace_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    outcome: str = "success",
    details: dict | None = None,
) -> AuditEvent:
    ev = AuditEvent(
        workspace_id=workspace_id,
        actor_id=actor_id,
        action=action,
        outcome=outcome,
        target_type=target_type,
        target_id=target_id,
        request_id=current_request_id(),
        client_ip=current_client_ip(),
        user_agent=current_user_agent(),
        details=_bounded(details or {}),
    )
    db.add(ev)
    return ev


def record_ctx(
    db: Session,
    ctx: WorkspaceContext,
    action: str,
    *,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    details: dict | None = None,
    outcome: str = "success",
) -> AuditEvent:
    return record(
        db,
        action=action,
        workspace_id=ctx.workspace_id,
        actor_id=ctx.user.id,
        target_type=target_type,
        target_id=target_id,
        outcome=outcome,
        details=details,
    )


def changes(before: dict[str, Any], after: dict[str, Any], fields: list[str]) -> dict[str, list[Any]]:
    """{field: [old, new]} for the allow-listed fields whose value changed."""
    return {f: [before.get(f), after.get(f)] for f in fields if before.get(f) != after.get(f)}


def list_events(
    db: Session,
    ctx: WorkspaceContext,
    page: PageParams,
    *,
    action: str | None,
    actor_id: uuid.UUID | None,
    target_type: str | None,
    target_id: uuid.UUID | None,
    request_id: str | None,
    since: datetime | None,
    until: datetime | None,
) -> Page[AuditEventOut]:
    from sqlalchemy import func

    conds = [AuditEvent.workspace_id == ctx.workspace_id]
    if action:
        conds.append(AuditEvent.action.like(action.replace("%", "") + "%"))  # prefix match: "issue." matches issue.*
    if actor_id:
        conds.append(AuditEvent.actor_id == actor_id)
    if target_type:
        conds.append(AuditEvent.target_type == target_type)
    if target_id:
        conds.append(AuditEvent.target_id == target_id)
    if request_id:
        conds.append(AuditEvent.request_id == request_id)
    if since:
        conds.append(AuditEvent.occurred_at >= since)
    if until:
        conds.append(AuditEvent.occurred_at <= until)
    total = db.scalar(select(func.count()).select_from(AuditEvent).where(*conds)) or 0
    rows = db.execute(
        select(AuditEvent, User.name)
        .outerjoin(User, User.id == AuditEvent.actor_id)
        .where(*conds)
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(page.limit)
        .offset(page.offset)
    ).all()
    items = [
        AuditEventOut(
            id=e.id,
            occurred_at=e.occurred_at,
            actor_id=e.actor_id,
            actor_name=name,
            action=e.action,
            outcome=e.outcome,
            target_type=e.target_type,
            target_id=e.target_id,
            request_id=e.request_id,
            client_ip=e.client_ip,
            details=e.details,
        )
        for e, name in rows
    ]
    return Page[AuditEventOut](items=items, total=total, limit=page.limit, offset=page.offset)
