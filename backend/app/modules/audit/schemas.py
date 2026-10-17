from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditEventOut(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    actor_id: uuid.UUID | None
    actor_name: str | None
    action: str
    outcome: str
    target_type: str | None
    target_id: uuid.UUID | None
    request_id: str | None
    client_ip: str | None
    details: dict


class AuditMeta(BaseModel):
    """What the audit page needs to build its filters, and the retention policy it should state."""

    actions: list[str]
    target_types: list[str]
    retention_days: int  # 0 = kept forever
    min_retention_days: int
