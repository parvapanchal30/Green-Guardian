from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, IdMixin, JsonType, TimestampMixin


class SpeciesCategory(StrEnum):
    TREE = "tree"
    CROP = "crop"
    PLANT = "plant"
    ORNAMENTAL = "ornamental"
    OTHER = "other"


class Species(IdMixin, TimestampMixin, Base):
    """Species / crop catalog. `workspace_id IS NULL` = global seed row visible to every workspace."""

    __tablename__ = "species"
    __table_args__ = (
        UniqueConstraint("workspace_id", "common_name", name="uq_species_workspace_common_name"),
        CheckConstraint("category IN (" + ", ".join(f"'{c.value}'" for c in SpeciesCategory) + ")", name="category"),
    )

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    common_name: Mapped[str] = mapped_column(String(200), nullable=False)
    scientific_name: Mapped[str | None] = mapped_column(String(200))
    attributes: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
