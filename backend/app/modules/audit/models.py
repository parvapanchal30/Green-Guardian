from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, event
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, IdMixin, JsonType
from app.core.timeutil import utcnow

OUTCOMES = ("success", "failure", "denied")


class AuditImmutable(Exception):
    """Audit records are append-only."""


class AuditEvent(IdMixin, Base):
    """One security or operational event. APPEND-ONLY: a database trigger rejects UPDATE/DELETE on PostgreSQL and an ORM
    guard rejects them everywhere; there is no API that modifies an audit record."""

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("outcome IN (" + ", ".join(f"'{o}'" for o in OUTCOMES) + ")", name="outcome"),
        Index("ix_audit_events_workspace_time", "workspace_id", "occurred_at"),
        Index("ix_audit_events_actor_time", "actor_id", "occurred_at"),
        Index("ix_audit_events_action_time", "action", "occurred_at"),
        Index("ix_audit_events_target", "target_type", "target_id"),
        Index("ix_audit_events_request", "request_id"),
    )

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    # RESTRICT: workspaces are archived, users are anonymised, never deleted; the trail must outlive both.
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), default="success", nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    request_id: Mapped[str | None] = mapped_column(String(64))
    client_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    details: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)


@event.listens_for(AuditEvent, "before_update")
@event.listens_for(AuditEvent, "before_delete")
def _forbid_mutation(mapper, connection, target):  # noqa: ARG001
    raise AuditImmutable("audit records cannot be modified or deleted")
