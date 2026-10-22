"""Lifecycle templates and transition rules: pure data and pure functions (no database, no framework).

The lifecycle is DATA, not code scattered through services (docs/PRD.md section 19, DOMAIN_MODEL.md): the ordered stages per
operating mode, and the exit stages per tracking mode, live in this one module. A workspace's mode picks the template.
Custom per-workspace templates are a later extension; today the templates are fixed and versioned with the code.

No agronomic durations are stored: "typical days per stage" would be domain knowledge we do not have and must not invent.

Rules (see `check_transition`):
* Stages advance. Skipping ahead is allowed (a mature tree is registered mature). Moving back, or leaving an exit stage, is a
  CORRECTION: it needs a written reason and a manager, and it is recorded as such, never hidden.
* Exits end the lifecycle: individuals can be `dead`, `removed` or `replaced`; populations (batches) can be `failed`,
  `removed` or `replaced`. `removed` and `replaced` are management decisions and need a manager; `dead` / `failed` are
  observations anyone who can record may report.
"""

from __future__ import annotations

from dataclasses import dataclass

GREEN_STAGES = ("planted", "growing", "mature", "maintained", "health_monitoring", "survival")
AGRI_STAGES = ("planted", "germination", "vegetative", "flowering", "fruiting", "harvest", "post_harvest")

EXITS_BY_TRACKING = {
    "individual": ("dead", "removed", "replaced"),
    "population": ("failed", "removed", "replaced"),
}
EXIT_STAGES = ("dead", "failed", "removed", "replaced")
BIOLOGICAL_LOSS_STAGES = ("dead", "failed")  # the exits that count against survival; removal/replacement do not
MANAGER_ONLY_EXITS = ("removed", "replaced")
STAGES_BY_MODE = {"green_management": GREEN_STAGES, "agricultural_production": AGRI_STAGES}
ALL_STAGES = tuple(dict.fromkeys((*GREEN_STAGES, *AGRI_STAGES, *EXIT_STAGES)))
HARVEST_STAGES = ("harvest", "post_harvest")
MIN_CORRECTION_NOTE = 10

LABELS = {
    "planted": "Planted",
    "growing": "Growing",
    "mature": "Mature",
    "maintained": "Maintained",
    "health_monitoring": "Health monitoring",
    "survival": "Survived establishment",
    "germination": "Germination",
    "vegetative": "Vegetative",
    "flowering": "Flowering",
    "fruiting": "Fruiting",
    "harvest": "Harvest",
    "post_harvest": "Post-harvest",
    "dead": "Dead",
    "failed": "Failed (batch lost)",
    "removed": "Removed",
    "replaced": "Replaced",
}


def stages_for(mode: str) -> tuple[str, ...]:
    return STAGES_BY_MODE.get(mode, GREEN_STAGES)


def exits_for(tracking_mode: str) -> tuple[str, ...]:
    return EXITS_BY_TRACKING.get(tracking_mode, EXITS_BY_TRACKING["individual"])


def is_exit(stage: str) -> bool:
    return stage in EXIT_STAGES


@dataclass(frozen=True)
class Problem:
    """Why a stage change is not allowed: `kind` is 'conflict' (the state forbids it) or 'invalid' (the request is wrong)."""

    kind: str
    code: str
    message: str
    allowed: tuple[str, ...] = ()


def next_choices(mode: str, tracking_mode: str, current: str) -> tuple[str, ...]:
    """The stages that can be recorded now WITHOUT a correction: later stages of the template and the exits."""
    if is_exit(current):
        return ()
    stages = stages_for(mode)
    later = stages[stages.index(current) + 1 :] if current in stages else stages
    return (*later, *exits_for(tracking_mode))


def check_transition(mode: str, tracking_mode: str, current: str, new: str, *, correction: bool) -> Problem | None:
    """None if recording `new` after `current` is allowed (the caller still checks roles and the note), else the problem."""
    valid = (*stages_for(mode), *exits_for(tracking_mode))
    if new not in valid:
        return Problem(
            "invalid",
            "invalid_stage",
            f"{new!r} is not a stage for this workspace and asset; use one of: {', '.join(valid)}",
            valid,
        )
    if new == current:
        return Problem("conflict", "same_stage", f"The asset is already in the {new!r} stage")
    if correction:
        return None
    choices = next_choices(mode, tracking_mode, current)
    if is_exit(current):
        return Problem(
            "conflict",
            "asset_exited",
            f"This asset has left the lifecycle ({current}); only a manager can reinstate it, as a correction with a reason",
        )
    if new not in choices:
        return Problem(
            "conflict",
            "backward_transition",
            f"Cannot move from {current!r} back to {new!r}; a manager can record that as a correction with a reason",
            choices,
        )
    return None
