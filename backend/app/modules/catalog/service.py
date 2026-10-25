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
    # Use in THIS workspace (live assets: not archived, not exited); plants = sum of estimated counts of batches.
    assets: int = 0
    plants: int | None = None


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


def _usage(db: Session, ctx: WorkspaceContext):
    """Per species: live assets of this workspace and, for population assets, their estimated plant count."""
    from app.modules.assets import lifecycle as lc
    from app.modules.assets.models import BiologicalAsset

    return (
        select(
            BiologicalAsset.species_id.label("species_id"),
            func.count().label("assets"),
            func.sum(BiologicalAsset.estimated_count).label("plants"),
        )
        .where(
            BiologicalAsset.workspace_id == ctx.workspace_id,
            BiologicalAsset.archived_at.is_(None),
            BiologicalAsset.current_stage.notin_(lc.EXIT_STAGES),
            BiologicalAsset.species_id.is_not(None),
        )
        .group_by(BiologicalAsset.species_id)
        .subquery()
    )


def list_species(
    db: Session,
    ctx: WorkspaceContext,
    page: PageParams,
    category: SpeciesCategory | None = None,
    q: str | None = None,
    in_use: bool | None = None,
) -> Page[SpeciesOut]:
    usage = _usage(db, ctx)
    stmt = (
        select(Species, usage.c.assets, usage.c.plants)
        .outerjoin(usage, usage.c.species_id == Species.id)
        .where(_visible(ctx))
    )
    if in_use is True:
        stmt = stmt.where(usage.c.assets > 0)
    if in_use is False:
        stmt = stmt.where(usage.c.assets.is_(None))
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
    rows = db.execute(stmt.order_by(Species.common_name, Species.id).limit(page.limit).offset(page.offset)).all()
    items = [
        to_out(r).model_copy(update={"assets": int(n or 0), "plants": int(p) if p is not None else None})
        for r, n, p in rows
    ]
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


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
