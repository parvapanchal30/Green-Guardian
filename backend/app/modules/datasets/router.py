from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, manager_ctx, viewer_ctx
from app.core.pagination import Page, PageParams, page_params

from . import service
from .schemas import (
    DatasetCreate,
    DatasetDetail,
    DatasetOut,
    DatasetTransition,
    EvidenceCreate,
    ReviewIn,
    ReviewOut,
    ReviewQueueSummary,
    SampleImport,
    SampleOut,
    SamplesCreate,
    SplitCreate,
    SplitDetail,
    SplitOut,
)

router = APIRouter(prefix="/workspaces/{ws}/datasets", tags=["datasets"])


@router.get("/licence-policy")
def licence_policy(ctx: WorkspaceContext = Depends(viewer_ctx)) -> dict[str, Any]:
    """The licences the catalog accepts, what an approval requires, and that there is no override."""
    return service.licence_policy()


@router.get("", response_model=Page[DatasetOut])
def list_datasets(
    status: str | None = Query(None, pattern="^(proposed|under_review|approved|rejected)$"),
    page: PageParams = Depends(page_params),
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    return service.list_datasets(db, ctx, page, status)


@router.post("", response_model=DatasetDetail, status_code=201)
def create_dataset(data: DatasetCreate, ctx: WorkspaceContext = Depends(manager_ctx), db: Session = Depends(get_db)):
    return service.create_dataset(db, ctx, data)


@router.get("/{dataset_id}", response_model=DatasetDetail)
def get_dataset(dataset_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)):
    return service.get_detail(db, ctx, dataset_id)


@router.post("/{dataset_id}/evidence", response_model=DatasetDetail, status_code=201)
def add_evidence(
    dataset_id: uuid.UUID,
    data: EvidenceCreate,
    ctx: WorkspaceContext = Depends(manager_ctx),
    db: Session = Depends(get_db),
):
    return service.add_evidence(db, ctx, dataset_id, data)


@router.post("/{dataset_id}/transitions", response_model=DatasetDetail)
def transition(
    dataset_id: uuid.UUID,
    data: DatasetTransition,
    ctx: WorkspaceContext = Depends(manager_ctx),
    db: Session = Depends(get_db),
):
    """under_review: a manager. approved / rejected: an owner or admin (403 otherwise). Approval is refused with the list
    of blockers while the evidence is incomplete or contradictory."""
    return service.transition(db, ctx, dataset_id, data)


@router.post("/{dataset_id}/samples", status_code=201)
def register_samples(
    dataset_id: uuid.UUID,
    data: SamplesCreate,
    ctx: WorkspaceContext = Depends(manager_ctx),
    db: Session = Depends(get_db),
):
    return service.register_samples(db, ctx, dataset_id, data)


@router.post("/{dataset_id}/samples/import")
def import_samples(
    dataset_id: uuid.UUID,
    data: SampleImport,
    ctx: WorkspaceContext = Depends(manager_ctx),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Validate a CSV (commit=false: preview, nothing written) or import it (commit=true: all or nothing, safe to retry).
    Imported labels are always unreviewed."""
    return service.import_samples(db, ctx, dataset_id, data)


@router.get("/{dataset_id}/samples", response_model=Page[SampleOut])
def list_samples(
    dataset_id: uuid.UUID,
    label_status: str | None = Query(None, pattern="^(unreviewed|under_review|accepted|rejected|corrected)$"),
    unlabelled: bool = False,
    page: PageParams = Depends(page_params),
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    return service.list_samples(db, ctx, dataset_id, page, label_status, unlabelled)


@router.post("/{dataset_id}/samples/{sample_id}/reviews", response_model=ReviewOut, status_code=201)
def review_sample(
    dataset_id: uuid.UUID,
    sample_id: uuid.UUID,
    data: ReviewIn,
    ctx: WorkspaceContext = Depends(manager_ctx),
    db: Session = Depends(get_db),
):
    """Change a label's review status. The reviewer recorded is the signed-in user; the qualification is only what they declare."""
    return service.review_sample(db, ctx, dataset_id, sample_id, data)


@router.get("/{dataset_id}/samples/{sample_id}/reviews", response_model=list[ReviewOut])
def sample_history(
    dataset_id: uuid.UUID,
    sample_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    return service.sample_history(db, ctx, dataset_id, sample_id)


@router.get("/{dataset_id}/review-summary", response_model=ReviewQueueSummary)
def review_summary(dataset_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)):
    return service.review_summary(db, ctx, dataset_id)


@router.get("/{dataset_id}/agreement")
def agreement(
    dataset_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Inter-reviewer agreement (Cohen's kappa) over samples decided by at least two different reviewers."""
    return service.agreement_of(db, ctx, dataset_id)


@router.get("/{dataset_id}/quality")
def quality(
    dataset_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)
) -> dict[str, Any]:
    return service.quality_of(db, ctx, dataset_id)


@router.post("/{dataset_id}/splits", response_model=SplitDetail, status_code=201)
def create_split(
    dataset_id: uuid.UUID,
    data: SplitCreate,
    ctx: WorkspaceContext = Depends(manager_ctx),
    db: Session = Depends(get_db),
):
    return service.create_split(db, ctx, dataset_id, data)


@router.get("/{dataset_id}/splits", response_model=list[SplitOut])
def list_splits(dataset_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)):
    return service.list_splits(db, ctx, dataset_id)


@router.get("/{dataset_id}/splits/{version}", response_model=SplitDetail)
def get_split(
    dataset_id: uuid.UUID, version: int, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)
):
    return service.get_split(db, ctx, dataset_id, version)


@router.get("/{dataset_id}/claim-readiness")
def claim_readiness(
    dataset_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """May a model performance claim be made on this data? Lists what blocks it today."""
    return service.claim_readiness(db, ctx, dataset_id)
