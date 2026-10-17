from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import Conflict, NotFound
from app.core.pagination import Page, PageParams
from app.core.schemas import SmallDict, StrictModel
from app.modules.audit import service as audit

from .models import Species, SpeciesCategory


class SpeciesCreate(StrictModel):
    category: SpeciesCategory
    common_name: str = Field(min_length=1, max_length=200)
    scientific_name: str | None = Field(default=None, max_length=200)
    attributes: SmallDict = Field(default_factory=dict)


class SpeciesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: SpeciesCategory
    common_name: str
    scientific_name: str | None
    is_global: bool = False


def _visible(ctx: WorkspaceContext):
    """Global seed rows plus this workspace's own species; never another workspace's."""
    return or_(Species.workspace_id.is_(None), Species.workspace_id == ctx.workspace_id)


def to_out(s: Species) -> SpeciesOut:
    return SpeciesOut(
        id=s.id,
        category=SpeciesCategory(s.category),
        common_name=s.common_name,
        scientific_name=s.scientific_name,
        is_global=s.workspace_id is None,
    )


def get_visible_species(db: Session, ctx: WorkspaceContext, species_id: uuid.UUID) -> Species:
    s = db.scalar(select(Species).where(Species.id == species_id, _visible(ctx)))
    if s is None:
        raise NotFound("Species not found", code="species_not_found")
    return s


def list_species(
    db: Session, ctx: WorkspaceContext, page: PageParams, category: SpeciesCategory | None = None, q: str | None = None
) -> Page[SpeciesOut]:
    stmt = select(Species).where(_visible(ctx))
    if category:
        stmt = stmt.where(Species.category == category.value)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Species.common_name).like(like),
                func.lower(func.coalesce(Species.scientific_name, "")).like(like),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Species.common_name, Species.id).limit(page.limit).offset(page.offset)).all()
    return Page(items=[to_out(r) for r in rows], total=total, limit=page.limit, offset=page.offset)


def create_species(db: Session, ctx: WorkspaceContext, data: SpeciesCreate) -> Species:
    clash = db.scalar(
        select(Species.id).where(_visible(ctx), func.lower(Species.common_name) == data.common_name.lower())
    )
    if clash:
        raise Conflict("A species with this name already exists (global or in this workspace)", code="species_exists")
    s = Species(
        workspace_id=ctx.workspace_id,
        category=data.category.value,
        common_name=data.common_name,
        scientific_name=data.scientific_name,
        attributes=data.attributes,
    )
    db.add(s)
    db.flush()
    audit.record_ctx(
        db,
        ctx,
        "species.create",
        target_type="species",
        target_id=s.id,
        details={"name": s.common_name, "category": s.category},
    )
    db.commit()
    return s
