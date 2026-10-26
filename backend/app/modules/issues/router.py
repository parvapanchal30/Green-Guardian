from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, manager_ctx, viewer_ctx, worker_ctx
from app.core.pagination import Page, PageParams, page_params

from . import service
from .models import IssueCategory, Severity
from .schemas import EvidenceAdd, IssueCreate, IssueDetail, IssueOut, IssueTransition, IssueUpdate, WorkflowOut

router = APIRouter(prefix="/workspaces/{ws}/issues", tags=["issues"])


@router.get("", response_model=Page[IssueOut])
def list_issues(
    state: str | None = None,
    is_open: bool | None = None,
    severity: Severity | None = None,
    category: IssueCategory | None = None,
    assignee: str | None = None,
    asset_id: uuid.UUID | None = None,
    q: str | None = None,
    waiting: bool | None = None,
    sort: Literal["recent", "severity"] = "recent",
    page: PageParams = Depends(page_params),
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    return service.list_issues(
        db,
        ctx,
        page,
        state=state,
        is_open=is_open,
        severity=severity,
        category=category,
        assignee=assignee,
        asset_id=asset_id,
        q=q,
        waiting=waiting,
        sort=sort,
    )


@router.post("", response_model=IssueDetail, status_code=status.HTTP_201_CREATED)
def create_issue(data: IssueCreate, ctx: WorkspaceContext = Depends(worker_ctx), db: Session = Depends(get_db)):
    return service.create_issue(db, ctx, data)


@router.get("/workflows", response_model=list[WorkflowOut])
def workflows(_ctx: WorkspaceContext = Depends(viewer_ctx)):
    """States and legal transitions per workflow, so a client never hard-codes them."""
    return service.workflows()


@router.get("/{issue_id}", response_model=IssueDetail)
def get_issue(issue_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)):
    return service.get_detail(db, ctx, issue_id)


@router.patch("/{issue_id}", response_model=IssueDetail)
def update_issue(
    issue_id: uuid.UUID, data: IssueUpdate, ctx: WorkspaceContext = Depends(manager_ctx), db: Session = Depends(get_db)
):
    return service.update_issue(db, ctx, issue_id, data)


@router.post("/{issue_id}/transitions", response_model=IssueDetail)
def transition_issue(
    issue_id: uuid.UUID,
    data: IssueTransition,
    ctx: WorkspaceContext = Depends(manager_ctx),
    db: Session = Depends(get_db),
):
    return service.transition(db, ctx, issue_id, data)


@router.post("/{issue_id}/evidence", response_model=IssueDetail)
def add_evidence(
    issue_id: uuid.UUID, data: EvidenceAdd, ctx: WorkspaceContext = Depends(worker_ctx), db: Session = Depends(get_db)
):
    return service.add_evidence(db, ctx, issue_id, data.observation_id)
