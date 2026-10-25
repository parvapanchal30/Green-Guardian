from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
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

from app.core.orm import Base, IdMixin, JsonType, TimestampMixin, UtcDateTime
from app.core.timeutil import utcnow

from .lifecycle import ALL_STAGES


class AssetKind(StrEnum):
    TREE = "tree"
    PLANT = "plant"
    CROP_BATCH = "crop_batch"
    SHRUB = "shrub"
    OTHER = "other"


class TrackingMode(StrEnum):
    INDIVIDUAL = "individual"  # one row = one living thing (a tree)
    POPULATION = "population"  # one row = many (a tomato batch with estimated_count)


class HealthBand(StrEnum):
    HEALTHY = "healthy"
    AT_RISK = "at_risk"
    CRITICAL = "critical"


def _in(values) -> str:
    return ", ".join(f"'{v.value}'" for v in values)


class BiologicalAsset(IdMixin, TimestampMixin, Base):
    """Trees, plants and crop batches share this one table (ADR-003)."""

    __tablename__ = "biological_assets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_biological_assets_workspace_id_id"),
        UniqueConstraint("workspace_id", "tag_code", name="uq_biological_assets_workspace_tag"),
        ForeignKeyConstraint(
            ["workspace_id", "location_id"],
            ["locations.workspace_id", "locations.id"],
            name="fk_biological_assets_location",
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"kind IN ({_in(AssetKind)})", name="kind"),
        CheckConstraint(f"tracking_mode IN ({_in(TrackingMode)})", name="tracking_mode"),
        CheckConstraint("estimated_count IS NULL OR estimated_count > 0", name="count_positive"),
        CheckConstraint("(tracking_mode = 'population') = (estimated_count IS NOT NULL)", name="population_has_count"),
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="coords_pair"),
        CheckConstraint("latitude IS NULL OR (latitude BETWEEN -90 AND 90)", name="lat_range"),
        CheckConstraint("longitude IS NULL OR (longitude BETWEEN -180 AND 180)", name="lon_range"),
        Index("ix_biological_assets_workspace_kind", "workspace_id", "kind"),
        Index("ix_biological_assets_workspace_location", "workspace_id", "location_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    species_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("species.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    tracking_mode: Mapped[str] = mapped_column(String(16), default=TrackingMode.INDIVIDUAL.value, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    tag_code: Mapped[str | None] = mapped_column(String(100))
    estimated_count: Mapped[int | None] = mapped_column(Integer)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    planted_at: Mapped[date | None] = mapped_column(Date)
    # A projection of the latest `lifecycle_events` row (ADR-055): only the lifecycle service writes it.
    current_stage: Mapped[str] = mapped_column(String(32), default="planted", nullable=False)
    attributes: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    archived_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


class AssetState(Base):
    """Current-state projection of an asset (ADR-004): rebuildable from observations, issues and tasks.

    Maintained synchronously inside the same transaction as the change that affects it.
    """

    __tablename__ = "asset_states"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["biological_assets.workspace_id", "biological_assets.id"],
            name="fk_asset_states_asset",
            ondelete="CASCADE",
        ),
        CheckConstraint("health_score IS NULL OR (health_score BETWEEN 0 AND 100)", name="health_range"),
        CheckConstraint(f"health_band IS NULL OR health_band IN ({_in(HealthBand)})", name="health_band"),
        Index("ix_asset_states_workspace_band", "workspace_id", "health_band"),
        Index("ix_asset_states_workspace_last_observed", "workspace_id", "last_observed_at"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    health_score: Mapped[float | None] = mapped_column(Float)
    health_band: Mapped[str | None] = mapped_column(String(16))
    health_observed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    last_observed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    open_issue_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    open_task_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_resolved_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow, nullable=False)


class LifecycleEvent(IdMixin, Base):
    """APPEND-ONLY lifecycle history of an asset (a trigger rejects UPDATE/DELETE on PostgreSQL).

    `assets.current_stage` always equals the stage of the asset's latest event (ordered by `entered_at`, then creation).
    Mistakes are corrected by a NEW event with `correction = true` and a written reason, never by editing a row.
    `entered_at` is when the asset entered the stage (it may be back-dated, but never into the future and never before
    the previous event); `created_at` is when it was recorded."""

    __tablename__ = "lifecycle_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["biological_assets.workspace_id", "biological_assets.id"],
            name="fk_lifecycle_events_asset",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"stage IN ({', '.join(repr(s) for s in ALL_STAGES)})", name="stage"),
        CheckConstraint("source IN ('manual', 'system')", name="source"),
        CheckConstraint("NOT correction OR (note IS NOT NULL AND length(note) >= 10)", name="correction_has_reason"),
        Index("ix_lifecycle_events_asset_entered", "workspace_id", "asset_id", "entered_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_stage: Mapped[str | None] = mapped_column(String(32))
    entered_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    correction: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, nullable=False)
