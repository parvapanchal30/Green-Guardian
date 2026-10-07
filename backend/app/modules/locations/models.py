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
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, IdMixin, JsonType, TimestampMixin


class LocationKind(StrEnum):
    SITE = "site"
    FIELD = "field"  # Agricultural Production vocabulary
    ZONE = "zone"  # Green Management vocabulary
    PLOT = "plot"


def _in(values) -> str:
    return ", ".join(f"'{v.value}'" for v in values)


class Location(IdMixin, TimestampMixin, Base):
    """One hierarchical table for sites, fields, zones and plots. Mode only changes the words (ADR-006).

    `latitude`/`longitude` are the portable source of truth. On PostgreSQL the migration also maintains a generated
    PostGIS `centroid` column with a GiST index (spatial queries); the ORM deliberately does not map it.
    """

    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_locations_workspace_id_id"),
        ForeignKeyConstraint(
            ["workspace_id", "parent_id"],
            ["locations.workspace_id", "locations.id"],
            name="fk_locations_parent",
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"kind IN ({_in(LocationKind)})", name="kind"),
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="coords_pair"),
        CheckConstraint("latitude IS NULL OR (latitude BETWEEN -90 AND 90)", name="lat_range"),
        CheckConstraint("longitude IS NULL OR (longitude BETWEEN -180 AND 180)", name="lon_range"),
        Index("ix_locations_workspace_kind", "workspace_id", "kind"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    attributes: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
