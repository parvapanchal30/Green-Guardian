from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, manager_ctx, viewer_ctx
from app.core.pagination import Page, PageParams, page_params

from . import runner, service
from .models import RecommendationStatus
from .schemas import AcceptRecommendation, AgentRunOut, DismissRecommendation, RecommendationOut, RuleInfo

router = APIRouter(prefix="/workspaces/{ws}", tags=["botanical-operations-agent"])


@router.get("/agent/rules", response_model=list[RuleInfo])
def agent_rules(ctx: WorkspaceContext = Depends(viewer_ctx)):
    """The rules in force, their method label (rule / statistical) and this workspace's thresholds."""
    cfg = runner.AgentSettings.from_workspace(ctx.workspace.settings)
    return [RuleInfo(**r) for r in runner.describe_rules(cfg)]


@router.post("/agent/run", response_model=AgentRunOut)
def run_agent(ctx: WorkspaceContext = Depends(manager_ctx), db: Session = Depends(get_db)):
    """Evaluate every active asset now. Idempotent: an already-open recommendation is never duplicated."""
    return service.run(db, ctx)


@router.get("/recommendations", response_model=Page[RecommendationOut])
def list_recommendations(
    status: RecommendationStatus | None = RecommendationStatus.OPEN,
    asset_id: uuid.UUID | None = None,
    page: PageParams = Depends(page_params),
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    return service.list_recommendations(db, ctx, page, status=status, asset_id=asset_id)


@router.post("/recommendations/{recommendation_id}/accept", response_model=RecommendationOut)
def accept(
    recommendation_id: uuid.UUID,
    data: AcceptRecommendation,
    ctx: WorkspaceContext = Depends(manager_ctx),
    db: Session = Depends(get_db),
):
    return service.accept(db, ctx, recommendation_id, data)


@router.post("/recommendations/{recommendation_id}/dismiss", response_model=RecommendationOut)
def dismiss(
    recommendation_id: uuid.UUID,
    data: DismissRecommendation,
    ctx: WorkspaceContext = Depends(manager_ctx),
    db: Session = Depends(get_db),
):
    return service.dismiss(db, ctx, recommendation_id, data)
