"""Task status transitions (data, like issue workflows)."""

from __future__ import annotations

from app.core.errors import Conflict

from .models import TaskStatus

TRANSITIONS: dict[str, tuple[str, ...]] = {
    TaskStatus.TODO.value: (
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.BLOCKED.value,
        TaskStatus.DONE.value,
        TaskStatus.CANCELLED.value,
    ),
    TaskStatus.IN_PROGRESS.value: (
        TaskStatus.TODO.value,
        TaskStatus.BLOCKED.value,
        TaskStatus.DONE.value,
        TaskStatus.CANCELLED.value,
    ),
    TaskStatus.BLOCKED.value: (TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value, TaskStatus.CANCELLED.value),
    TaskStatus.DONE.value: (TaskStatus.IN_PROGRESS.value,),  # reopen
    TaskStatus.CANCELLED.value: (TaskStatus.TODO.value,),  # reopen
}
REOPENING = {
    (TaskStatus.DONE.value, TaskStatus.IN_PROGRESS.value),
    (TaskStatus.CANCELLED.value, TaskStatus.TODO.value),
}


def allowed(status: str) -> tuple[str, ...]:
    return TRANSITIONS.get(status, ())


def check(from_status: str, to_status: str) -> None:
    if to_status not in allowed(from_status):
        raise Conflict(
            f"cannot move a task from '{from_status}' to '{to_status}'",
            code="invalid_transition",
            extra={"allowed": list(allowed(from_status))},
        )
