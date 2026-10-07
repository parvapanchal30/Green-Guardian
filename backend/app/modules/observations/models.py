from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, IdMixin, JsonType
from app.core.timeutil import utcnow


class ObservationKind(StrEnum):
    INSPECTION = "inspection"
    HEALTH = "health"
    GROWTH = "growth"
    SYMPTOM = "symptom"
    ENVIRONMENT = "environment"
    HARVEST = "harvest"
    OTHER = "other"


class ObservationSource(StrEnum):
    HUMAN = "human"
    MODEL = "model"
    SENSOR = "sensor"
    IMPORT = "import"
    AGENT = "agent"


def _in(values) -> str:
    return ", ".join(f"'{v.value}'" for v in values)


class Observation(IdMixin, Base):
    """The universal evidence unit. APPEND-ONLY: a database trigger rejects UPDATE and DELETE; corrections are new
    rows that point at the row they supersede."""

    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_observations_workspace_id_id"),
        ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["biological_assets.workspace_id", "biological_assets.id"],
            name="fk_observations_asset",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "location_id"],
            ["locations.workspace_id", "locations.id"],
            name="fk_observations_location",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "supersedes_id"],
            ["observations.workspace_id", "observations.id"],
            name="fk_observations_supersedes",
            ondelete="RESTRICT",
        ),
        CheckConstraint("asset_id IS NOT NULL OR location_id IS NOT NULL", name="has_subject"),
        CheckConstraint("health_score IS NULL OR (health_score BETWEEN 0 AND 100)", name="health_range"),
        CheckConstraint(f"kind IN ({_in(ObservationKind)})", name="kind"),
        CheckConstraint(f"source IN ({_in(ObservationSource)})", name="source"),
        Index("ix_observations_asset_observed", "workspace_id", "asset_id", "observed_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    location_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # RESTRICT, not SET NULL: observations are append-only, so a user with history is anonymised, never deleted
    observer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(16), default=ObservationKind.HEALTH.value, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default=ObservationSource.HUMAN.value, nullable=False)
    method: Mapped[str | None] = mapped_column(String(100))
    health_score: Mapped[float | None] = mapped_column(Float)
    symptoms: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    # Photo/evidence METADATA only: [{name, content_type, url, caption}]. Upload/storage arrives with the storage slice.
    attachments: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
