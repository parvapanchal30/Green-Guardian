"""Map read model for the `assets` layer.

Everything is decided in the database: scope (location / kind), the chip filter, the viewport, and the chip counts.
On PostgreSQL the viewport uses the PostGIS `centroid` columns and their GiST indexes (`ST_Intersects` against an
envelope); on SQLite (fast test mode) the same predicate is expressed on latitude/longitude. An asset without its own
coordinates is drawn at the centre of its location, and says so (`position_source`).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from sqlalchemy import ColumnElement, and_, case, func, literal_column, or_, select
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import CapabilityUnavailable, NotFound
from app.modules.assets.models import AssetState, BiologicalAsset
from app.modules.catalog.models import Species
from app.modules.locations.models import Location

from .layers import LAYER_INDEX
from .schemas import AssetProps, Feature, FeatureCollection, FilterCounts, MapFilter, Point

BBox = tuple[float, float, float, float]
MAX_FEATURES = 5000

A, L, S, ST = BiologicalAsset, Location, Species, AssetState
LAT = func.coalesce(A.latitude, L.latitude)
LON = func.coalesce(A.longitude, L.longitude)


def _join(stmt):
    return (
        stmt.select_from(A)
        .outerjoin(L, and_(L.workspace_id == A.workspace_id, L.id == A.location_id))
        .outerjoin(S, S.id == A.species_id)
        .outerjoin(ST, ST.asset_id == A.id)
    )


def _scope(ctx: WorkspaceContext, location_id: uuid.UUID | None, kind: str | None) -> list:
    conds = [A.workspace_id == ctx.workspace_id, A.archived_at.is_(None)]
    if location_id:
        conds.append(A.location_id == location_id)
    if kind:
        conds.append(A.kind == kind)
    return conds


def _viewport(db: Session, bbox: BBox):
    min_lon, min_lat, max_lon, max_lat = bbox
    if db.get_bind().dialect.name == "postgresql":
        env = func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
        own: ColumnElement = literal_column("biological_assets.centroid")
        loc: ColumnElement = literal_column("locations.centroid")
        return or_(
            func.ST_Intersects(own, env),  # GiST index on biological_assets.centroid
            and_(own.is_(None), func.ST_Intersects(loc, env)),  # GiST index on locations.centroid
        )
    return and_(LAT.between(min_lat, max_lat), LON.between(min_lon, max_lon))


CHIPS: dict[MapFilter, Callable[[], object]] = {
    MapFilter.ALL: lambda: True,
    MapFilter.HEALTHY: lambda: ST.health_band == "healthy",
    MapFilter.AT_RISK: lambda: ST.health_band == "at_risk",
    MapFilter.CRITICAL: lambda: ST.health_band == "critical",
    MapFilter.OPEN_ISSUES: lambda: ST.open_issue_count > 0,
    MapFilter.TASKS: lambda: ST.open_task_count > 0,
}


def _counts(db: Session, scope: list) -> FilterCounts:
    placed = and_(LAT.is_not(None), LON.is_not(None))

    def n(cond):
        return func.count().filter(and_(placed, cond))

    row = db.execute(
        _join(
            select(
                n(True),
                n(CHIPS[MapFilter.HEALTHY]()),
                n(CHIPS[MapFilter.AT_RISK]()),
                n(CHIPS[MapFilter.CRITICAL]()),
                n(CHIPS[MapFilter.OPEN_ISSUES]()),
                n(CHIPS[MapFilter.TASKS]()),
                func.count().filter(~placed),
            )
        ).where(*scope)
    ).one()
    return FilterCounts(
        all=row[0], healthy=row[1], at_risk=row[2], critical=row[3], open_issues=row[4], tasks=row[5], unlocated=row[6]
    )


def assets_layer(
    db: Session,
    ctx: WorkspaceContext,
    *,
    chip: MapFilter,
    location_id: uuid.UUID | None,
    kind: str | None,
    bbox: BBox | None,
    limit: int,
) -> FeatureCollection:
    scope = _scope(ctx, location_id, kind)
    counts = _counts(db, scope)

    where = [*scope, LAT.is_not(None), LON.is_not(None), CHIPS[chip]()]
    if bbox:
        where.append(_viewport(db, bbox))
    rows = db.execute(
        _join(
            select(
                A.id,
                A.label,
                A.kind,
                A.tracking_mode,
                A.estimated_count,
                S.common_name,
                A.location_id,
                L.name,
                ST.health_band,
                ST.health_score,
                func.coalesce(ST.open_issue_count, 0),
                func.coalesce(ST.open_task_count, 0),
                LAT,
                LON,
                case((A.latitude.is_not(None), "asset"), else_="location"),
            )
        )
        .where(*where)
        .order_by(A.id)
        .limit(min(limit, MAX_FEATURES) + 1)
    ).all()

    cap = min(limit, MAX_FEATURES)
    truncated = len(rows) > cap
    features = [
        Feature(
            id=r[0],
            geometry=Point(coordinates=(r[13], r[12])),
            properties=AssetProps(
                asset_id=r[0],
                label=r[1],
                kind=r[2],
                tracking_mode=r[3],
                estimated_count=r[4],
                species=r[5],
                location_id=r[6],
                location_name=r[7],
                health_band=r[8],
                health_score=r[9],
                open_issue_count=r[10],
                open_task_count=r[11],
                position_source=r[14],
            ),
        )
        for r in rows[:cap]
    ]
    box = None
    if features:
        lons = [f.geometry.coordinates[0] for f in features]
        lats = [f.geometry.coordinates[1] for f in features]
        box = (min(lons), min(lats), max(lons), max(lats))
    return FeatureCollection(
        layer="assets", filter=chip, features=features, counts=counts, bbox=box, truncated=truncated
    )


PROVIDERS = {"assets": assets_layer}


def layer_features(db: Session, ctx: WorkspaceContext, layer: str, **params) -> FeatureCollection:
    info = LAYER_INDEX.get(layer)
    if info is None:
        raise NotFound(f"unknown map layer {layer!r}")
    if not info.available or layer not in PROVIDERS:
        raise CapabilityUnavailable(
            f"The {info.label} layer is planned ({info.stage.upper()}) and needs: {info.requires}."
        )
    return PROVIDERS[layer](db, ctx, **params)
