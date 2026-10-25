from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, manager_ctx, viewer_ctx
from app.core.pagination import Page, PageParams, page_params

from . import service
from .models import SpeciesCategory
from .service import SpeciesCreate, SpeciesOut

router = APIRouter(prefix="/workspaces/{ws}/species", tags=["catalog"])


@router.get("", response_model=Page[SpeciesOut])
def list_species(
    category: SpeciesCategory | None = None,
    q: str | None = None,
    in_use: bool | None = None,
    page: PageParams = Depends(page_params),
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    return service.list_species(db, ctx, page, category, q, in_use)


@router.post("", response_model=SpeciesOut, status_code=status.HTTP_201_CREATED)
def create_species(data: SpeciesCreate, ctx: WorkspaceContext = Depends(manager_ctx), db: Session = Depends(get_db)):
    return service.to_out(service.create_species(db, ctx, data))
