"""Human-readable per-workspace keys (GG-001, T-014) allocated from `workspaces.key_counters`."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Workspace


def next_key(db: Session, workspace_id: uuid.UUID, counter: str, prefix: str) -> str:
    """Atomic within the caller's transaction: the workspace row is locked (`FOR UPDATE`) until commit, so two
    concurrent requests can never receive the same number."""
    ws = db.execute(select(Workspace).where(Workspace.id == workspace_id).with_for_update()).scalar_one()
    counters = dict(ws.key_counters or {})
    number = int(counters.get(counter, 0)) + 1
    counters[counter] = number
    ws.key_counters = counters  # reassign: in-place JSON mutation is not tracked
    db.flush()
    return f"{prefix}-{number:03d}"
