"""Capability registry: which intelligence features are actually live.

The frontend renders a real layout for every entry and swaps in the live feature only when
`available` is true; otherwise it shows "Coming soon". Nothing here may be marked available until
the backing implementation exists and is wired (ADR-008).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    key: str
    label: str
    technique: str
    stage: str
    available: bool
    reason: str | None = None


REGISTRY: tuple[Capability, ...] = (
    Capability(
        "botanical_agent_rules",
        "Botanical Operations Agent (rules)",
        "Rules + statistics",
        "mvp",
        False,
        "Rules engine exists as a library; recommendations API and worker are not wired yet",
    ),
    Capability("weather_context", "Weather context", "Weather provider", "mvp", True),
    Capability("disease_detection", "Disease Detection", "Computer vision", "v2", False, "Planned (V2)"),
    Capability("growth_prediction", "Growth Prediction", "Machine learning", "v2", False, "Planned (V2)"),
    Capability("survival_prediction", "Survival Prediction", "Machine learning", "v2", False, "Planned (V2)"),
    Capability("yield_prediction", "Yield Prediction", "Machine learning", "v2", False, "Planned (V2)"),
    Capability("harvest_prediction", "Harvest Prediction", "Machine learning", "v2", False, "Planned (V2)"),
    Capability("crop_recommendation", "Crop Recommendation", "Recommendation engine", "v3", False, "Planned (V3)"),
    Capability(
        "irrigation_recommendation", "Irrigation Recommendation", "Water balance + rules", "v3", False, "Planned (V3)"
    ),
    Capability("profitability", "Profitability", "Financial model", "v3", False, "Planned (V3)"),
    Capability("optimization", "Operational Optimization", "Optimization", "v4", False, "Planned (V4)"),
)


def effective_capabilities(overrides: dict | None) -> list[Capability]:
    """Workspace overrides may only *disable* a live capability (kill switch); they can never
    enable one that the code registry says is unavailable."""
    overrides = overrides or {}
    out = []
    for c in REGISTRY:
        if c.available and overrides.get(c.key) is False:
            out.append(Capability(c.key, c.label, c.technique, c.stage, False, "Disabled for this workspace"))
        else:
            out.append(c)
    return out
