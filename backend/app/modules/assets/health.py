"""Health bands are derived from a 0-100 score and are configurable per workspace (docs/PRD.md section 23)."""

from __future__ import annotations

from .models import HealthBand

DEFAULT_HEALTHY_MIN = 70.0
DEFAULT_CRITICAL_BELOW = 40.0


def health_band(
    score: float | None,
    *,
    healthy_min: float = DEFAULT_HEALTHY_MIN,
    critical_below: float = DEFAULT_CRITICAL_BELOW,
) -> HealthBand | None:
    """Healthy >= 70, At risk 40-69, Critical < 40 by default. None when there is no score (unknown, not healthy)."""
    if score is None:
        return None
    if score < critical_below:
        return HealthBand.CRITICAL
    if score < healthy_min:
        return HealthBand.AT_RISK
    return HealthBand.HEALTHY
