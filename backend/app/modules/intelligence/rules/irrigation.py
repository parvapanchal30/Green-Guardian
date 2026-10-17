"""Irrigation deferral (RULE, advisory, forecast-based).

WHAT THIS RULE IS: when a watering task is about to fall due and the weather FORECAST says a meaningful amount of rain
is likely, suggest that a person consider postponing that task. Nothing is postponed automatically.

WHAT IT DELIBERATELY IS NOT: an estimate of how much water a plant needs, or of how wet the soil is. A rainfall forecast
does not establish soil moisture (interception, runoff, drainage, soil type and plant uptake all intervene), and a
forecast can be wrong. The weather model's own top-1-cm soil moisture value is shown as context but is never a trigger:
it is a coarse model output, not a measurement, and it is not specific to the asset.

Inputs the system has: the forecast (rain mm, rain probability, temperature), the open watering task and its due date,
when the asset was last watered (a completed watering task), recorded symptoms and open issues.
Inputs it does NOT have (listed in every suggestion's evidence): measured soil moisture, observed rainfall, species or
crop water requirements and growth stage, soil type, irrigation method and volumes.

Safeguard: the suggestion is withheld when the asset shows signs of water stress (for example wilting), because the
plant may genuinely need water now whatever the forecast says.

Pure: no database and no I/O. The forecast arrives on the snapshot, fetched by the runner through the weather port.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .base import AssetSnapshot, Finding, Skip

NOT_KNOWN = (
    "measured soil moisture (the value shown is a coarse weather-model estimate for the top 1 cm, "
    "not a sensor reading)",
    "observed rainfall (only a forecast is available)",
    "species or crop water requirements and growth stage",
    "soil type, irrigation method and the volume applied",
)
SOIL_NOTE = (
    "modelled by the weather provider for the top 1 cm of soil; not measured, not specific to this asset, "
    "shown for context only and never used as a trigger"
)
FORECAST_WINDOW_H = 24  # the weather context summarises the next 24 hours


@dataclass(frozen=True)
class IrrigationDeferral:
    min_rain_mm: float = 5.0
    min_probability_pct: float = 70.0
    defer_hours: int = 24
    lookahead_hours: int = 24
    key: str = "irrigation_defer"

    def evaluate(self, assets: list[AssetSnapshot], now: datetime) -> list[Finding]:
        return self.evaluate_detailed(assets, now)[0]

    def evaluate_detailed(self, assets: list[AssetSnapshot], now: datetime) -> tuple[list[Finding], list[Skip]]:
        findings: list[Finding] = []
        skips: list[Skip] = []
        horizon = min(self.lookahead_hours, FORECAST_WINDOW_H)  # we only have a 24 h summary
        for a in assets:
            if not a.open_water_tasks:
                continue
            candidates = []
            for t in a.open_water_tasks:
                if t.status != "todo":
                    skips.append(Skip(a.asset_id, self.key, "task_started_or_blocked"))
                elif t.due_at is None:
                    skips.append(Skip(a.asset_id, self.key, "no_due_date"))
                elif not (now - timedelta(hours=24) <= t.due_at <= now + timedelta(hours=horizon)):
                    continue  # due too far ahead (or long overdue): the forecast window does not speak to it
                else:
                    candidates.append(t)
            if not candidates:
                continue
            if a.water_stress_signs:
                skips.extend(Skip(a.asset_id, self.key, "water_stress_signs") for _ in candidates)
                continue
            if a.weather_status == "no_location" or (a.latitude is None or a.longitude is None):
                skips.extend(Skip(a.asset_id, self.key, "no_location") for _ in candidates)
                continue
            w = a.weather
            if w is None:
                skips.extend(Skip(a.asset_id, self.key, "weather_unavailable") for _ in candidates)
                continue
            if w.rain_next_24h_mm is None or w.max_rain_probability_pct is None:
                skips.extend(Skip(a.asset_id, self.key, "forecast_incomplete") for _ in candidates)
                continue
            if w.rain_next_24h_mm < self.min_rain_mm or w.max_rain_probability_pct < self.min_probability_pct:
                skips.extend(Skip(a.asset_id, self.key, "below_threshold") for _ in candidates)
                continue
            for t in candidates:
                assert t.due_at is not None
                hours_until_due = round((t.due_at - now).total_seconds() / 3600, 1)
                due_text = f"in {hours_until_due:g} h" if hours_until_due >= 0 else f"{-hours_until_due:g} h ago"
                soil = (
                    f" The weather model also estimates the top 1 cm of soil at {w.soil_moisture_top:g} m3/m3 "
                    "(a model estimate, shown for context only)."
                    if w.soil_moisture_top is not None
                    else ""
                )
                findings.append(
                    Finding(
                        rule_key=self.key,
                        method="rule",
                        subject_ids=(a.asset_id,),
                        subject_key=f"{a.asset_id}:{t.task_id}",
                        title=(
                            f"Consider deferring watering of {a.label} ({t.key}): "
                            f"{w.rain_next_24h_mm:g} mm rain forecast"
                        ),
                        explanation=(
                            "ADVISORY, based on a weather forecast and not on a measurement of soil moisture. "
                            f"{w.rain_next_24h_mm:g} mm of rain is forecast in the next 24 h with up to "
                            f"{w.max_rain_probability_pct:g}% probability (thresholds: {self.min_rain_mm:g} mm and "
                            f"{self.min_probability_pct:g}%), and watering task {t.key} is due {due_text}. No signs of "
                            "water stress are recorded for this asset."
                            f"{soil} Not known to this rule: measured soil moisture, observed rainfall, species water "
                            "needs, soil type and irrigation volumes."
                        ),
                        severity="low",
                        proposed_action={
                            "create": "defer_task",
                            "task_id": t.task_id,
                            "task_key": t.key,
                            "defer_hours": self.defer_hours,
                            "asset_id": a.asset_id,
                        },
                        evidence={
                            "kind": "advisory_forecast_based",
                            "forecast": {
                                "source": w.source,
                                "as_of": w.as_of.isoformat(),
                                "rain_next_24h_mm": w.rain_next_24h_mm,
                                "max_rain_probability_pct": w.max_rain_probability_pct,
                                "temperature_c": w.temperature_c,
                                "soil_moisture_top_modelled": w.soil_moisture_top,
                                "soil_moisture_note": SOIL_NOTE,
                            },
                            "thresholds": {
                                "min_rain_mm": self.min_rain_mm,
                                "min_probability_pct": self.min_probability_pct,
                                "lookahead_hours": horizon,
                            },
                            "task": {
                                "id": t.task_id,
                                "key": t.key,
                                "due_at": t.due_at.isoformat(),
                                "hours_until_due": hours_until_due,
                            },
                            "last_watered_at": a.last_watered_at.isoformat() if a.last_watered_at else None,
                            "water_stress_signs": [],
                            "location": {
                                "latitude": a.latitude,
                                "longitude": a.longitude,
                                "source": a.position_source,
                            },
                            "not_known": list(NOT_KNOWN),
                        },
                    )
                )
        return findings, skips
