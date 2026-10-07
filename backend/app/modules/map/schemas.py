from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class MapFilter(StrEnum):
    ALL = "all"
    HEALTHY = "healthy"
    AT_RISK = "at_risk"
    CRITICAL = "critical"
    OPEN_ISSUES = "open_issues"
    TASKS = "tasks"


class LayerInfo(BaseModel):
    """One entry of the layer registry. Layers other than `available` ones are declared so the UI can show them as
    planned; requesting their features returns 501 capability_unavailable (never invented data)."""

    key: str
    label: str
    description: str
    available: bool
    stage: str  # mvp | v2 | v3
    geometry: Literal["point", "polygon", "raster"]
    requires: str | None = None  # what must exist before the layer can be built


class Point(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]  # [longitude, latitude] (GeoJSON order)


class AssetProps(BaseModel):
    asset_id: uuid.UUID
    label: str
    kind: str
    tracking_mode: str
    estimated_count: int | None
    species: str | None
    location_id: uuid.UUID | None
    location_name: str | None
    health_band: str | None
    health_score: float | None
    open_issue_count: int
    open_task_count: int
    position_source: Literal["asset", "location"]  # own coordinates, or the centre of its location


class Feature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: uuid.UUID
    geometry: Point
    properties: AssetProps


class FilterCounts(BaseModel):
    """Counts for the filter chips: within the active location/kind scope, ignoring the chip and the viewport."""

    all: int
    healthy: int
    at_risk: int
    critical: int
    open_issues: int
    tasks: int
    unlocated: int  # assets in scope with no coordinates anywhere (cannot be drawn)


class FeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    layer: str
    filter: MapFilter
    features: list[Feature]
    counts: FilterCounts
    bbox: tuple[float, float, float, float] | None  # [minLon, minLat, maxLon, maxLat] of the returned features
    truncated: bool
