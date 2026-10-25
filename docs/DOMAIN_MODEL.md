# Domain Model

## Core graph

```
Organization ─┬─ Membership ── User
              └─ Workspace (mode: green_management | agricultural_production; capability flags; thresholds)
                    └─ Project
                         ├─ Location (Field | Zone | Site; hierarchical; polygon)
                         └─ Planting (species/crop, planted_at, area, source)
                              └─ Batch / BiologicalAsset
                                   ├─ LifecycleEvent*      (append-only)
                                   ├─ Observation*         (append-only; evidence)
                                   │    ├─ HealthRecord*   (derived/explicit score over time)
                                   │    ├─ GrowthRecord*
                                   │    └─ Attachment*     (photos)
                                   ├─ Issue* ─ IssueStatusHistory*
                                   ├─ Task*  ─ TaskStatusHistory*
                                   ├─ Treatment / Inspection / Harvest
                                   └─ Outcome (via resolved issues, harvests, survival)
Recommendation  (agent output → accepted → Issue/Task)
Prediction      (reserved; model output with uncertainty + provenance)
EnvironmentReading / WeatherRecord (per location)
Report
```
`*` = many, historical.

## Key modelling decisions

1. **One `BiologicalAsset` entity, `kind` discriminator.** kinds: `tree`, `plant`, `crop_batch`, `shrub`, `other`. `tracking_mode`: `individual` | `population`. A population asset has `estimated_count` and (optionally) child individuals via `parent_asset_id`. Avoids separate Tree/Crop/Plant tables; screens differ by `kind` + workspace mode, not by schema.
2. **Locations are a single hierarchical table** (`kind`: site, field, zone, plot), polygon geometry, parent pointer. "Field" (agri) and "Zone" (green) are vocabulary over the same thing.
3. **Species/Crop is one catalog** (`category`: tree, crop, ornamental…) with lifecycle template reference and agronomic parameters.
4. **State is time-aware.** Current values live in the `asset_state` projection; truth is the append-only history. Health/growth are records with `observed_at`, `source` (human, model, sensor), `method`.
5. **Observation is the universal evidence unit.** Humans, disease models, sensors and inspections all produce Observations; Issues cite Observations as evidence; rules read them.
6. **Issue and Task are first-class with status history**; polymorphic *subject* (asset | location | batch) via `subject_type + subject_id` plus `issue_asset` for clusters.
7. **Lifecycle & workflow are data** (templates), validated by services.
8. **Recommendation ≠ Prediction ≠ Rule output.** Recommendation = suggested action with explanation & method; Prediction = quantitative forecast with interval & model version.
9. **Soft delete** assets/locations (`archived_at`); history preserved. Hard delete only by workspace purge.

## Enumerations (initial)

- **Workspace mode:** `green_management`, `agricultural_production`
- **Role:** `owner`, `admin`, `manager`, `worker`, `viewer`
- **Lifecycle stages:** Green — `planted, growing, mature, maintained, health_monitoring, survival` ; Agri — `planted, germination, vegetative, flowering, fruiting, harvest, post_harvest` ; Exit — `dead, removed, replaced, failed`
- **Health band (derived):** `healthy (≥70) | at_risk (40–69) | critical (<40) | unknown`
- **Issue category:** `disease, pest, nutrient, water_stress, irrigation_failure, physical_damage, growth_anomaly, harvest_readiness, maintenance, other`
- **Issue severity:** `low, medium, high, critical`
- **Issue state (template-defined):** `open, investigating, field_inspection, treatment, monitoring, resolved, assigned, fixed, verified, pending, inspection, ready, harvested, closed_wont_fix`
- **Task type:** `water, fertilize, inspect, treat, prune, plant, replace, harvest, monitor, other`
- **Task status:** `todo, in_progress, blocked, done, cancelled`; **priority** `p1..p4`
- **Observation source:** `human, model, sensor, import, agent`
- **Recommendation status:** `open, accepted, dismissed, expired`; **method:** `rule, statistical, model, llm`

## Invariants

- Every tenant entity belongs to exactly one workspace; cross-workspace references are forbidden (FK + service check).
- **Action** (ADR-059) is a record of work done to an asset (kind, product, quantity with unit, when, who, optional issue and task); append-only with manager corrections. **Verification** of an issue is a RULE comparing the latest recorded health score before the first action with the latest observation after the last one; a plant issue closed as fixed or mitigated needs that follow-up observation.
- **Inspection schedule** (ADR-062): a routine for one asset or location (every N days, created K days ahead, for an assignee) that turns each due date into an ordinary task; its occurrences are append-only; no pile-up while a task is open; a plant that leaves the lifecycle stops its schedule.
- **Harvest** is a stage and a *record*: `HarvestRecord` (ADR-056) holds quantity, unit, date and grade; corrections are new records that supersede (once); only kg and t are added together; the dashboard Yield KPI is the recorded weight of the last 12 months, never an estimate.
- An asset's `current_stage` always equals its latest `LifecycleEvent.stage` (built, ADR-055: one transaction, row-locked, tested as an invariant). Stages advance (skipping ahead is allowed); moving back or reinstating an exited asset is a *correction* (manager, written reason, flagged in the history). Exits: individuals `dead`/`removed`/`replaced`, populations `failed`/`removed`/`replaced`; `removed`/`replaced` need a manager. An exited asset is excluded from active counts, inspections, agent runs and the map; it still has its history. No agronomic stage durations are stored (none are known).
- An Issue's `state` always equals its latest `IssueStatusHistory.to_state` and is a legal transition per its workflow template.
- Observation rows are immutable; corrections are new rows referencing `supersedes_id`.
- Health score ∈ [0,100]; growth percent ∈ [0,100] (or null).
- Recommendation dedupe key unique among *open* recommendations.
- At most one `AgentRun` with status `running` per workspace (partial unique index); a recommendation's `agent_run_id`, if set, names a run of the same workspace (composite FK).

## Implemented in the first vertical slice (2026-10-07)

`Workspace → Location → BiologicalAsset → Observation → Issue → Task`, plus `AssetState` (projection) and `Recommendation`. A tree and a crop batch are the **same entity** (`kind`, `tracking_mode`); the agricultural example (crop batch of 84,200 plants in a field) is covered by the same tests as the tree.

- **Observation** is the single evidence unit and carries the optional health score; there is no separate HealthRecord yet.
- **AssetState** (current health/band, last observed, open issue/task counts, last resolved) is updated synchronously in the transaction that changes its inputs and is rebuildable (`rebuild_state`, tested for equality with the maintained values).
- **Issue** lifecycle is defined by a *workflow* chosen by category and workspace mode (plant health, field disease, infrastructure, harvest readiness). Reopening clears the resolution; history keeps everything.
- **Task** has its own status workflow; completing a task may record a follow-up observation, which is how acting on an issue changes the asset's state.
- **Recommendation** is produced only by rules (`method` ∈ rule/statistical), de-duplicated, explained, and acted on by a person.
- **Dataset / DatasetEvidence / DatasetSample / LabelReview / DatasetSplit** (Stage D, ADR-044): a catalog of data sources with licence evidence and approval, their items with a review state, the append-only review history, and numbered checksummed splits. A `synthetic` dataset is a test fixture and is never biological data.
- **AgentRun** (Stage C) is one evaluation of one workspace, manual or scheduled: trigger, status (`running`, `succeeded`, `failed`), who or which worker ran it, start/finish, counts (assets evaluated, findings, recommendations created and expired), the rules in force with their versions and parameters, diagnostics (weather status, skipped cases with reasons) and a redacted error. It is the agent's execution history and the scheduler's only state.
- **Recommendation lifecycle** (ADR-041): `open` → `accepted` | `dismissed` | `expired`. It records the producing run and rule version, structured evidence (`evaluated_at`, rule, inputs), and later an **outcome** (`task_completed`, `task_cancelled`, `issue_resolved`, `issue_closed`, `deferral_applied`; the first one wins). `proposed_action.create` is `issue`, `task` or `defer_task` (move a not-yet-started watering task's due date; irrigation advice only).
- Invariants now enforced by the database: tenant-consistent links (composite FKs), immutable history (triggers), one open recommendation per dedupe key, consistent issue resolution columns, health score 0–100.
