from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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

from app.core.orm import Base, IdMixin, JsonType
from app.core.timeutil import utcnow

DATASET_STATUSES = ("proposed", "under_review", "approved", "rejected")
LABEL_STATUSES = ("unreviewed", "under_review", "accepted", "rejected", "corrected")


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


class Dataset(IdMixin, Base):
    """A catalog entry: where a dataset comes from, what licence covers it (images and annotations separately), and the
    approval state. `kind='synthetic'` marks generated test fixtures, which are never biological data. Immutable apart
    from `status`; a changed licence or source is a NEW version, so approvals always refer to what was verified."""

    __tablename__ = "datasets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_datasets_workspace_id_id"),
        UniqueConstraint("workspace_id", "name", "version", name="uq_datasets_name_version"),
        CheckConstraint("kind IN ('real', 'synthetic')", name="kind"),
        CheckConstraint(f"status IN ({_in(DATASET_STATUSES)})", name="status"),
        CheckConstraint("commercial_use IN ('yes', 'no', 'unknown')", name="commercial_use"),
        CheckConstraint("redistribution IN ('yes', 'no', 'unknown')", name="redistribution"),
        CheckConstraint(
            "image_origin IN ('publisher_created', 'third_party_licensed', 'third_party_scraped', 'unknown')",
            name="image_origin",
        ),
        CheckConstraint("status <> 'approved' OR kind = 'synthetic' OR approved_by IS NOT NULL", name="approved_by"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    licence_spdx: Mapped[str] = mapped_column(String(60), nullable=False)
    images_licence_spdx: Mapped[str] = mapped_column(String(60), nullable=False)
    annotations_licence_spdx: Mapped[str | None] = mapped_column(String(60))
    has_annotations: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Where the IMAGES came from. A publisher's licence only covers images the publisher had the right to license.
    image_origin: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    attribution_required: Mapped[bool | None] = mapped_column(Boolean)
    attribution_text: Mapped[str | None] = mapped_column(Text)
    commercial_use: Mapped[str] = mapped_column(String(8), nullable=False, default="unknown")
    redistribution: Mapped[str] = mapped_column(String(8), nullable=False, default="unknown")
    intended_use: Mapped[str] = mapped_column(Text, nullable=False, default="")
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DatasetEvidence(IdMixin, Base):
    """APPEND-ONLY licence evidence: one row per source read (a trigger rejects UPDATE/DELETE). Wrong evidence is
    superseded by a newer row, never edited."""

    __tablename__ = "dataset_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "dataset_id"],
            ["datasets.workspace_id", "datasets.id"],
            name="fk_dataset_evidence_dataset",
            ondelete="CASCADE",
        ),
        CheckConstraint("scope IN ('images', 'annotations', 'both')", name="scope"),
        Index("ix_dataset_evidence_dataset", "dataset_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    scope: Mapped[str] = mapped_column(String(12), nullable=False)
    licence_spdx: Mapped[str] = mapped_column(String(60), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    official: Mapped[bool] = mapped_column(Boolean, nullable=False)
    accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DatasetStatusHistory(IdMixin, Base):
    """APPEND-ONLY approval history, with the blockers that were open at the time (a trigger rejects UPDATE/DELETE)."""

    __tablename__ = "dataset_status_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "dataset_id"],
            ["datasets.workspace_id", "datasets.id"],
            name="fk_dataset_status_history_dataset",
            ondelete="CASCADE",
        ),
        Index("ix_dataset_status_history_dataset_at", "dataset_id", "at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(Text)
    blockers: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DatasetSample(IdMixin, Base):
    """One item (an image). Metadata and fingerprints only: the files themselves are not stored here."""

    __tablename__ = "dataset_samples"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_dataset_samples_workspace_id_id"),
        UniqueConstraint("dataset_id", "external_id", name="uq_dataset_samples_external"),
        ForeignKeyConstraint(
            ["workspace_id", "dataset_id"],
            ["datasets.workspace_id", "datasets.id"],
            name="fk_dataset_samples_dataset",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"label_status IN ({_in(LABEL_STATUSES)})", name="label_status"),
        CheckConstraint("file_status IS NULL OR file_status IN ('ok', 'invalid')", name="file_status"),
        Index("ix_dataset_samples_dataset_status", "dataset_id", "label_status"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    external_id: Mapped[str] = mapped_column(String(300), nullable=False)
    group_key: Mapped[str | None] = mapped_column(String(200))
    label: Mapped[str | None] = mapped_column(String(120))
    label_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unreviewed")
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    phash: Mapped[str | None] = mapped_column(String(16))
    file_status: Mapped[str | None] = mapped_column(String(8))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    provenance: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LabelReview(IdMixin, Base):
    """APPEND-ONLY record of every label status change: who, when, what changed, and the evidence (a trigger rejects
    UPDATE/DELETE). `reviewer_qualification` is what the reviewer DECLARED; the system does not verify it."""

    __tablename__ = "label_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "sample_id"],
            ["dataset_samples.workspace_id", "dataset_samples.id"],
            name="fk_label_reviews_sample",
            ondelete="CASCADE",
        ),
        Index("ix_label_reviews_sample_at", "sample_id", "at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    sample_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reviewer_qualification: Mapped[str | None] = mapped_column(String(300))
    from_status: Mapped[str] = mapped_column(String(16), nullable=False)
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    from_label: Mapped[str | None] = mapped_column(String(120))
    to_label: Mapped[str | None] = mapped_column(String(120))
    evidence: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DatasetSplit(IdMixin, Base):
    """APPEND-ONLY versioned split (a trigger rejects UPDATE/DELETE). The manifest maps sample id to split name; the
    checksum covers seed, fractions and assignment, so a version can be reproduced and verified."""

    __tablename__ = "dataset_splits"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "dataset_id"],
            ["datasets.workspace_id", "datasets.id"],
            name="fk_dataset_splits_dataset",
            ondelete="CASCADE",
        ),
        UniqueConstraint("dataset_id", "version", name="uq_dataset_splits_version"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    fractions: Mapped[dict] = mapped_column(JsonType, nullable=False)
    include_unreviewed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    manifest: Mapped[dict] = mapped_column(JsonType, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    stats: Mapped[dict] = mapped_column(JsonType, nullable=False)
    warnings: Mapped[list] = mapped_column(JsonType, nullable=False)
    leakage_violations: Mapped[list] = mapped_column(JsonType, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
