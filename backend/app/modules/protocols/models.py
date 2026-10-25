from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, IdMixin, JsonType, UtcDateTime
from app.core.timeutil import utcnow


class EvaluationProtocol(IdMixin, Base):
    """APPEND-ONLY protocol version (a trigger rejects UPDATE/DELETE). A change is a new version of the same `key`, which
    supersedes the older one and needs fresh sign-offs. Its approval state is computed from the sign-offs, never stored."""

    __tablename__ = "evaluation_protocols"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_evaluation_protocols_workspace_id_id"),
        UniqueConstraint("workspace_id", "key", "version", name="uq_evaluation_protocols_key_version"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[dict] = mapped_column(JsonType, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, nullable=False)


class ProtocolSignoff(IdMixin, Base):
    """APPEND-ONLY sign-off by a person acting in one required role. `qualification_verified` is locked to false by a CHECK
    constraint: the application can record what a signer declares but has no way to verify it, and a future verification
    feature must remove that lock deliberately."""

    __tablename__ = "protocol_signoffs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "protocol_id"],
            ["evaluation_protocols.workspace_id", "evaluation_protocols.id"],
            name="fk_protocol_signoffs_protocol",
            ondelete="CASCADE",
        ),
        CheckConstraint("role IN ('plant_pathologist', 'data_owner', 'independent_evaluator')", name="role"),
        CheckConstraint("decision IN ('approve', 'reject')", name="decision"),
        CheckConstraint("qualification_verified = false", name="qualification_unverifiable"),
        Index("ix_protocol_signoffs_protocol_at", "protocol_id", "at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    protocol_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    decision: Mapped[str] = mapped_column(String(8), nullable=False)
    signer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    declared_qualification: Mapped[str | None] = mapped_column(String(300))
    qualification_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, nullable=False)
