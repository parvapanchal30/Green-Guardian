from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import WorkspaceContext, viewer_ctx
from app.core.errors import Unprocessable
from app.modules.assets.models import AssetKind

from . import service
from .layers import LAYERS
from .schemas import FeatureCollection, LayerInfo, MapFilter

router = APIRouter(prefix="/workspaces/{ws}/map", tags=["map"])


@router.get("/layers", response_model=list[LayerInfo])
def list_layers(ctx: WorkspaceContext = Depends(viewer_ctx)):
    """The layer registry: what the map can show now and what is planned (never served with placeholder data)."""
    return LAYERS


def _parse_bbox(raw: str | None) -> service.BBox | None:
    if raw is None:
        return None
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in raw.split(","))
    except ValueError:
        raise Unprocessable("bbox must be 'minLon,minLat,maxLon,maxLat'") from None
    if not (-180 <= min_lon <= max_lon <= 180 and -90 <= min_lat <= max_lat <= 90):
        raise Unprocessable("bbox is out of range or its minimum exceeds its maximum")
    return min_lon, min_lat, max_lon, max_lat


@router.get("/layers/{layer}", response_model=FeatureCollection)
def layer_features(
    layer: str,
    filter: MapFilter = MapFilter.ALL,
    location_id: uuid.UUID | None = None,
    kind: AssetKind | None = None,
    bbox: str | None = Query(default=None, description="minLon,minLat,maxLon,maxLat"),
    limit: int = Query(default=2000, ge=1, le=service.MAX_FEATURES),
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    """GeoJSON features for one layer, filtered and viewport-clipped in the database."""
    return service.layer_features(
        db,
        ctx,
        layer,
        chip=filter,
        location_id=location_id,
        kind=kind.value if kind else None,
        bbox=_parse_bbox(bbox),
        limit=limit,
    )
