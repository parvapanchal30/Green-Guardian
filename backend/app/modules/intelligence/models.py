from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, IdMixin, JsonType
from app.core.timeutil import utcnow


class RecommendationStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class Method(StrEnum):
    """Provenance of an output. The MVP only ever produces RULE or STATISTICAL (docs/AI_ARCHITECTURE.md)."""

    RULE = "rule"
    STATISTICAL = "statistical"
    MODEL = "model"
    LLM = "llm"


def _in(values) -> str:
    return ", ".join(f"'{v.value}'" for v in values)


class Recommendation(IdMixin, Base):
    """A suggested action with its explanation. A person accepts it (creating an issue or task through the normal
    services) or dismisses it; nothing is created automatically."""

    __tablename__ = "recommendations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["biological_assets.workspace_id", "biological_assets.id"],
            name="fk_recommendations_asset",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"method IN ({_in(Method)})", name="method"),
        CheckConstraint(f"status IN ({_in(RecommendationStatus)})", name="status"),
        CheckConstraint("severity IN ('low','medium','high','critical')", name="severity"),
        # one OPEN recommendation per (workspace, dedupe key): re-running the agent never spams
        Index(
            "uq_recommendations_open_dedupe",
            "workspace_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status = 'open'"),
            sqlite_where=text("status = 'open'"),
        ),
        Index("ix_recommendations_workspace_status", "workspace_id", "status"),
        Index("ix_recommendations_workspace_dedupe_decided", "workspace_id", "dedupe_key", "decided_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    rule_key: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    proposed_action: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=RecommendationStatus.OPEN.value, nullable=False)
    accepted_entity_type: Mapped[str | None] = mapped_column(String(16))
    accepted_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    dismissed_reason: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
