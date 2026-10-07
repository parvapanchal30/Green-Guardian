from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, manager_ctx, viewer_ctx, worker_ctx
from app.core.pagination import Page, PageParams, page_params

from . import service
from .models import TaskStatus, TaskType
from .schemas import TaskCreate, TaskDetail, TaskOut, TaskTransition, TaskUpdate

router = APIRouter(prefix="/workspaces/{ws}/tasks", tags=["tasks"])


@router.get("", response_model=Page[TaskOut])
def list_tasks(
    status: TaskStatus | None = None,
    is_open: bool | None = None,
    assignee: str | None = None,
    issue_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    type: TaskType | None = None,  # noqa: A002
    overdue: bool | None = None,
    q: str | None = None,
    page: PageParams = Depends(page_params),
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    return service.list_tasks(
        db,
        ctx,
        page,
        status=status,
        is_open=is_open,
        assignee=assignee,
        issue_id=issue_id,
        asset_id=asset_id,
        type=type,
        overdue=overdue,
        q=q,
    )


@router.post("", response_model=TaskDetail, status_code=status.HTTP_201_CREATED)
def create_task(data: TaskCreate, ctx: WorkspaceContext = Depends(manager_ctx), db: Session = Depends(get_db)):
    return service.create_task(db, ctx, data)


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(task_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)):
    return service.get_detail(db, ctx, task_id)


@router.patch("/{task_id}", response_model=TaskDetail)
def update_task(
    task_id: uuid.UUID, data: TaskUpdate, ctx: WorkspaceContext = Depends(manager_ctx), db: Session = Depends(get_db)
):
    return service.update_task(db, ctx, task_id, data)


@router.post("/{task_id}/transitions", response_model=TaskDetail)
def transition_task(
    task_id: uuid.UUID, data: TaskTransition, ctx: WorkspaceContext = Depends(worker_ctx), db: Session = Depends(get_db)
):
    """Assignee (worker or above) or any manager. Completing can carry a follow-up observation (updates the asset)."""
    return service.transition(db, ctx, task_id, data)
