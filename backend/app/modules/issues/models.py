from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, IdMixin, UtcDateTime
from app.core.timeutil import utcnow


class IssueCategory(StrEnum):
    DISEASE = "disease"
    PEST = "pest"
    NUTRIENT = "nutrient"
    WATER_STRESS = "water_stress"
    IRRIGATION_FAILURE = "irrigation_failure"
    PHYSICAL_DAMAGE = "physical_damage"
    GROWTH_ANOMALY = "growth_anomaly"
    HARVEST_READINESS = "harvest_readiness"
    MAINTENANCE = "maintenance"
    OTHER = "other"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IssueSource(StrEnum):
    MANUAL = "manual"
    OBSERVATION = "observation"
    AGENT = "agent"
    MODEL = "model"


class ResolutionOutcome(StrEnum):
    FIXED = "fixed"
    MITIGATED = "mitigated"
    NO_ACTION_NEEDED = "no_action_needed"
    WONT_FIX = "wont_fix"
    DUPLICATE = "duplicate"


def _in(values) -> str:
    return ", ".join(f"'{v.value}'" for v in values)


class Issue(IdMixin, Base):
    """A Botanical Issue: a first-class domain object, not a generic ticket (docs/PRD.md section 20).

    `state` is validated against the issue's *workflow* (app/modules/issues/workflows.py), which is data-like and
    selected by category and workspace mode, so irrigation failures, pest outbreaks, harvest readiness and
    infrastructure faults fit without schema changes. An issue is OPEN while `resolved_at IS NULL`.
    """

    __tablename__ = "issues"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_issues_workspace_id_id"),
        UniqueConstraint("workspace_id", "key", name="uq_issues_workspace_key"),
        ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["biological_assets.workspace_id", "biological_assets.id"],
            name="fk_issues_asset",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "location_id"],
            ["locations.workspace_id", "locations.id"],
            name="fk_issues_location",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "origin_observation_id"],
            ["observations.workspace_id", "observations.id"],
            name="fk_issues_origin_observation",
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"category IN ({_in(IssueCategory)})", name="category"),
        CheckConstraint(f"severity IN ({_in(Severity)})", name="severity"),
        CheckConstraint(f"source IN ({_in(IssueSource)})", name="source"),
        CheckConstraint(
            f"resolution_outcome IS NULL OR resolution_outcome IN ({_in(ResolutionOutcome)})", name="outcome"
        ),
        CheckConstraint("(resolved_at IS NULL) = (resolution_outcome IS NULL)", name="resolution_consistent"),
        Index("ix_issues_workspace_state_severity", "workspace_id", "state", "severity"),
        Index("ix_issues_workspace_asset", "workspace_id", "asset_id"),
        Index("ix_issues_workspace_assignee", "workspace_id", "assignee_id"),
        Index("ix_issues_workspace_open", "workspace_id", "resolved_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    workflow_key: Mapped[str] = mapped_column(String(48), nullable=False)
    state: Mapped[str] = mapped_column(String(48), nullable=False)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    location_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(16), default=IssueSource.MANUAL.value, nullable=False)
    origin_observation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL"), index=True
    )
    opened_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    resolution_outcome: Mapped[str | None] = mapped_column(String(24))
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class IssueObservation(Base):
    """Evidence: observations attached to an issue (the originating one is linked automatically)."""

    __tablename__ = "issue_observations"
    __table_args__ = (
        PrimaryKeyConstraint("issue_id", "observation_id", name="pk_issue_observations"),
        ForeignKeyConstraint(
            ["workspace_id", "issue_id"],
            ["issues.workspace_id", "issues.id"],
            name="fk_issue_observations_issue",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "observation_id"],
            ["observations.workspace_id", "observations.id"],
            name="fk_issue_observations_observation",
            ondelete="RESTRICT",
        ),
    )

    issue_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    observation_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    added_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    added_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, nullable=False)


class IssueStatusHistory(IdMixin, Base):
    """APPEND-ONLY audit of every state change (a trigger rejects UPDATE/DELETE). The first row has from_state NULL."""

    __tablename__ = "issue_status_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "issue_id"],
            ["issues.workspace_id", "issues.id"],
            name="fk_issue_status_history_issue",
            ondelete="CASCADE",
        ),
        Index("ix_issue_status_history_issue_at", "issue_id", "at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    issue_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(48))
    to_state: Mapped[str] = mapped_column(String(48), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    note: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, nullable=False)
