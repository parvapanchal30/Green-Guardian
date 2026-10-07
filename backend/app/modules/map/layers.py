"""Layer registry. The map is a set of layers over one workspace-scoped, PostGIS-backed read model.

Adding a layer later = one entry here + one provider in `service.PROVIDERS`. Only `assets` exists at MVP. The others
are declared as planned (they depend on prediction/sensing capabilities that are roadmap items) and must never be
served with placeholder data.
"""

from __future__ import annotations

from .schemas import LayerInfo

LAYERS: list[LayerInfo] = [
    LayerInfo(
        key="assets",
        label="Biological assets",
        description="Trees, plants and crop batches with their current health, issues and tasks.",
        available=True,
        stage="mvp",
        geometry="point",
    ),
    LayerInfo(
        key="disease_hotspots",
        label="Disease hotspots",
        description="Clusters of detected disease.",
        available=False,
        stage="v2",
        geometry="polygon",
        requires="Disease detection",
    ),
    LayerInfo(
        key="soil_moisture",
        label="Soil moisture",
        description="Soil moisture across zones.",
        available=False,
        stage="v2",
        geometry="raster",
        requires="Soil moisture readings",
    ),
    LayerInfo(
        key="irrigation",
        label="Irrigation",
        description="Irrigation status and plans.",
        available=False,
        stage="v3",
        geometry="polygon",
        requires="Irrigation records and a water-balance model",
    ),
    LayerInfo(
        key="growth",
        label="Growth",
        description="Growth against expectation.",
        available=False,
        stage="v2",
        geometry="point",
        requires="Growth prediction",
    ),
    LayerInfo(
        key="canopy",
        label="Canopy",
        description="Canopy cover.",
        available=False,
        stage="v2",
        geometry="raster",
        requires="Canopy measurements",
    ),
    LayerInfo(
        key="survival_risk",
        label="Survival risk",
        description="Predicted survival risk per asset.",
        available=False,
        stage="v2",
        geometry="point",
        requires="Survival prediction",
    ),
    LayerInfo(
        key="yield",
        label="Yield",
        description="Expected yield per field.",
        available=False,
        stage="v2",
        geometry="polygon",
        requires="Yield prediction",
    ),
]

LAYER_INDEX = {layer.key: layer for layer in LAYERS}
