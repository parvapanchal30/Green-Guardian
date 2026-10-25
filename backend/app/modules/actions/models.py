from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

from app.core.orm import Base, IdMixin, UtcDateTime
from app.core.timeutil import utcnow

# What can be DONE to an asset. Looking at it is an observation, harvesting is a harvest record: neither is an action.
KINDS = ("treat", "water", "fertilize", "prune", "pest_control", "weed", "mulch", "replant", "other")
UNITS = ("l", "ml", "kg", "g", "count")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class ActionRecord(IdMixin, Base):
    """APPEND-ONLY record of work done to an asset (ADR-059): what, with what, how much, when and by whom, optionally
    for an issue or a task. A trigger rejects UPDATE/DELETE on PostgreSQL.

    A mistake is corrected by a NEW row whose `supersedes_id` names the record it replaces (`withdrawn` marks a record
    that should not have existed). A record can be superseded once; the effective records are the rows nobody
    supersedes. `performed_at` is when the work was done, `created_at` when it was recorded."""

    __tablename__ = "actions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_actions_workspace_id_id"),
        ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["biological_assets.workspace_id", "biological_assets.id"],
            name="fk_actions_asset",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "issue_id"],
            ["issues.workspace_id", "issues.id"],
            name="fk_actions_issue",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "task_id"], ["tasks.workspace_id", "tasks.id"], name="fk_actions_task", ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["workspace_id", "follow_up_task_id"],
            ["tasks.workspace_id", "tasks.id"],
            name="fk_actions_follow_up_task",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "supersedes_id"],
            ["actions.workspace_id", "actions.id"],
            name="fk_actions_supersedes",
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"kind IN ({_in(KINDS)})", name="kind"),
        CheckConstraint(f"unit IS NULL OR unit IN ({_in(UNITS)})", name="unit"),
        CheckConstraint("(quantity IS NULL) = (unit IS NULL)", name="quantity_has_unit"),
        CheckConstraint("quantity IS NULL OR quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "supersedes_id IS NULL OR (note IS NOT NULL AND length(note) >= 10)", name="correction_has_reason"
        ),
        CheckConstraint("NOT withdrawn OR supersedes_id IS NOT NULL", name="withdrawal_is_correction"),
        Index("ix_actions_asset_performed", "workspace_id", "asset_id", "performed_at"),
        Index("ix_actions_issue", "workspace_id", "issue_id"),
        Index(
            "uq_actions_supersedes",
            "workspace_id",
            "supersedes_id",
            unique=True,
            postgresql_where=text("supersedes_id IS NOT NULL"),
            sqlite_where=text("supersedes_id IS NOT NULL"),
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    issue_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    product: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(8))
    performed_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    # RESTRICT, not SET NULL: the table is append-only, so a person with history is anonymised, never deleted
    performed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    note: Mapped[str | None] = mapped_column(Text)
    follow_up_task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    withdrawn: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, nullable=False)
