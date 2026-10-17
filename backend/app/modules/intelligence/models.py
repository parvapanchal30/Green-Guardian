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
    Integer,
    String,
    Text,
    UniqueConstraint,
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


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RunTrigger(StrEnum):
    MANUAL = "manual"  # a person pressed "Run checks"
    SCHEDULED = "scheduled"  # the worker


class Outcome(StrEnum):
    """What eventually happened to the work a recommendation led to (recorded by the task/issue services)."""

    TASK_COMPLETED = "task_completed"
    TASK_CANCELLED = "task_cancelled"
    ISSUE_RESOLVED = "issue_resolved"
    ISSUE_CLOSED = "issue_closed"
    DEFERRAL_APPLIED = "deferral_applied"


def _in(values) -> str:
    return ", ".join(f"'{v.value}'" for v in values)


class AgentRun(IdMixin, Base):
    """One evaluation of one workspace by the Botanical Operations Agent (manual or scheduled): what ran, with which
    rules and parameters, what it found, and how it ended. A partial unique index allows only ONE running row per
    workspace, which is what prevents overlapping runs across processes."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_agent_runs_workspace_id_id"),
        CheckConstraint(f"trigger IN ({_in(RunTrigger)})", name="trigger"),
        CheckConstraint(f"status IN ({_in(RunStatus)})", name="status"),
        Index(
            "uq_agent_runs_one_running",
            "workspace_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
        Index("ix_agent_runs_workspace_started", "workspace_id", "started_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=RunStatus.RUNNING.value, nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    worker_id: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evaluated_assets: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    findings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recommendations_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recommendations_expired: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # rules in force for this run: [{key, version, method, parameters}] (rule configuration is versioned by what ran)
    rules: Mapped[list] = mapped_column(JsonType, default=list, nullable=False)
    # weather status, skipped-asset reasons ... anything needed to explain what the run did and did not do
    diagnostics: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)


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
        ForeignKeyConstraint(
            ["workspace_id", "agent_run_id"],
            ["agent_runs.workspace_id", "agent_runs.id"],
            name="fk_recommendations_agent_run",
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"outcome IS NULL OR outcome IN ({_in(Outcome)})", name="outcome"),
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
    # traceability: which run produced it (None = evaluated inline when an observation was saved) and under which rule
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    rule_version: Mapped[int | None] = mapped_column(Integer)
    # follow-up: what eventually happened to the work this recommendation led to
    outcome: Mapped[str | None] = mapped_column(String(24))
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome_detail: Mapped[str | None] = mapped_column(Text)
