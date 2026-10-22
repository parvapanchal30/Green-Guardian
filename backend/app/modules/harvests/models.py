from __future__ import annotations

import uuid
from datetime import datetime

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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, IdMixin
from app.core.timeutil import utcnow

UNITS = ("kg", "t", "count", "l")
MASS_TO_TONNES = {"kg": 0.001, "t": 1.0}  # the only units that can be added together


class HarvestRecord(IdMixin, Base):
    """APPEND-ONLY record of what was harvested from an asset (ADR-056). A trigger rejects UPDATE/DELETE on PostgreSQL.

    A mistake is corrected by a NEW row whose `supersedes_id` names the record it replaces (quantity 0 withdraws it).
    A record can be superseded once; the effective figures are the rows nobody supersedes. `harvested_at` is when the
    produce was harvested, `created_at` when it was recorded."""

    __tablename__ = "harvest_records"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_harvest_records_workspace_id_id"),
        ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["biological_assets.workspace_id", "biological_assets.id"],
            name="fk_harvest_records_asset",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "supersedes_id"],
            ["harvest_records.workspace_id", "harvest_records.id"],
            name="fk_harvest_records_supersedes",
            ondelete="RESTRICT",
        ),
        CheckConstraint("unit IN ('kg', 't', 'count', 'l')", name="unit"),
        CheckConstraint("quantity >= 0", name="quantity_nonnegative"),
        CheckConstraint("supersedes_id IS NOT NULL OR quantity > 0", name="new_record_positive"),
        CheckConstraint(
            "supersedes_id IS NULL OR (note IS NOT NULL AND length(note) >= 10)", name="correction_has_reason"
        ),
        Index("ix_harvest_records_asset_harvested", "workspace_id", "asset_id", "harvested_at"),
        Index(
            "uq_harvest_records_supersedes",
            "workspace_id",
            "supersedes_id",
            unique=True,
            postgresql_where=text("supersedes_id IS NOT NULL"),
            sqlite_where=text("supersedes_id IS NOT NULL"),
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    harvested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(8), nullable=False)
    grade: Mapped[str | None] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
