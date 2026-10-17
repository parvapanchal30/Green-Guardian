from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
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

from app.core.orm import Base, IdMixin
from app.core.timeutil import utcnow

ALLOWED_TYPES = ("image/jpeg", "image/png", "image/webp")


class Evidence(IdMixin, Base):
    """A stored image attached to an asset, optionally to the observation and/or issue it documents.

    The image bytes live in the object store under `storage_key`; this row is the index and the provenance
    (who, when, exact bytes via `sha256`). Rows are never updated except to soft-delete; the blob is retained until a
    purge job removes it. It is also the substrate for later pipeline stages (labelling, detection), which will
    reference `(workspace_id, id)` rather than copy images.
    """

    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_evidence_workspace_id_id"),
        UniqueConstraint("storage_key", name="uq_evidence_storage_key"),
        ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["biological_assets.workspace_id", "biological_assets.id"],
            name="fk_evidence_asset",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "observation_id"],
            ["observations.workspace_id", "observations.id"],
            name="fk_evidence_observation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "issue_id"],
            ["issues.workspace_id", "issues.id"],
            name="fk_evidence_issue",
            ondelete="RESTRICT",
        ),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        CheckConstraint("width > 0 AND height > 0", name="dimensions_positive"),
        CheckConstraint("content_type IN (" + ", ".join(f"'{t}'" for t in ALLOWED_TYPES) + ")", name="content_type"),
        Index("ix_evidence_asset_created", "workspace_id", "asset_id", "created_at"),
        Index("ix_evidence_issue", "workspace_id", "issue_id"),
        Index("ix_evidence_observation", "workspace_id", "observation_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    observation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    issue_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(200), nullable=False)
    # Display only. Never used to build a path.
    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    caption: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
