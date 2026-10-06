# GreenGuardian — Product Requirements Document

> Status: v1.0 (initial). Source of truth for *what* GreenGuardian is meant to become.
> Companion docs: [ARCHITECTURE](ARCHITECTURE.md) · [DOMAIN_MODEL](DOMAIN_MODEL.md) · [DATABASE_SCHEMA](DATABASE_SCHEMA.md) · [API_SPECIFICATION](API_SPECIFICATION.md) · [FRONTEND_ARCHITECTURE](FRONTEND_ARCHITECTURE.md) · [AI_ARCHITECTURE](AI_ARCHITECTURE.md) · [MVP_SCOPE](MVP_SCOPE.md) · [DECISION_LOG](DECISION_LOG.md)

---

## 1. Product overview

GreenGuardian is an **operating system for managing biological assets** — trees, plants, crops, batches, fields, orchards, parks, campuses, plantations — through their whole lifecycle. It is *not* a tree dashboard, an agriculture dashboard, a task manager, or a chatbot. It is a system that:

1. **models** biological assets as a time-aware graph,
2. **understands their state** from observations,
3. **manages the operations** around them (issues, tasks, inspections, treatments, harvests),
4. **uses intelligence** to determine what should happen next, and
5. **closes the loop** by checking whether the action worked.

## 2. Vision

Move users up a ladder, one rung at a time:

| Rung | Question | Capability |
|---|---|---|
| 1 | What exists? | Asset registry, map |
| 2 | What is its state? | Observations, health, growth (time-series) |
| 3 | What is going wrong? | Rules/anomaly detection → Botanical Issues |
| 4 | What will happen? | Survival / growth / yield / harvest prediction (V2+) |
| 5 | What should we do? | Botanical Operations Agent → next best action |
| 6 | Did it work? | Outcome monitoring, issue resolution verification |
| 7 | How do we optimize the whole system? | Resource allocation, crop selection, profit optimization (V3) |

The MVP delivers rungs 1–3 and the *operational* half of 5–6 (rule-driven recommendations → tasks → verification), with UI surfaces already in place for rungs 4 and 7.

## 3. Problem statement

- Green-space managers and farmers track assets in spreadsheets, WhatsApp groups and paper registers. State is overwritten, history is lost, and nobody can answer "how was this tree 30 days ago?".
- Problems are noticed late (inspection gaps, silent disease spread, irrigation failure) because nothing continuously asks "what needs attention?".
- Observations don't turn into action: a photo of a sick tree sits in a chat; no owner, no due date, no verification.
- Generic ticketing tools lack biological context (lifecycle stage, species, season, zone, evidence); generic farm tools ignore urban/municipal green management. The two worlds share the same underlying model but are served by unrelated products.
- "AI" tools are usually chatbots bolted onto dashboards; they do not integrate with the operational system and over-claim.

## 4. Target users

| Persona | Mode | Needs |
|---|---|---|
| **Ward / urban-forestry officer** | Green | Know which of 18k trees need action; prioritize limited crews; report survival & canopy |
| **Campus / park / society manager** | Green | Simple registry, inspection schedule, issue tracking |
| **NGO afforestation lead** | Green | Survival and impact reporting for donors, geotagged evidence |
| **Farm owner / commercial grower** | Agri | Field/batch health, yield & harvest outlook, cost/revenue |
| **Farm supervisor** | Agri | Daily task list, issue triage, worker assignment |
| **Field worker** (low connectivity, phone) | Both | See assigned tasks, log observation + photo in <30 s, offline-tolerant |
| **Analyst / auditor** | Both | Read-only dashboards, exports, reports from real records |

## 5. Operating modes

One platform, two **workspace modes** (a workspace-level setting that selects vocabulary, default KPIs, dashboard composition and lifecycle template — *not* a separate codebase).

- **Mode A — Green Management** (`green_management`): lifecycle `PLANTED → GROWING → MATURE → MAINTAINED → HEALTH MONITORING → SURVIVAL`; KPIs **Survival, Health, Growth, Canopy, Coverage**.
- **Mode B — Agricultural Production** (`agricultural_production`): lifecycle `PLANTED → GERMINATION → VEGETATIVE → FLOWERING → FRUITING → HARVEST → POST-HARVEST`; KPIs **Growth, Health, Yield, Harvest, Revenue**.

A workspace may later enable both (e.g. a university with an orchard) — modelled as a `mode` per **Project**, defaulting from the workspace.

## 6. Product thesis

> Biological assets share one structure — *asset → lifecycle → observations → state → issues → tasks → actions → outcome*. Harvest is one lifecycle stage, not a separate product. Build that structure once; let modes be configuration; let intelligence plug into the same loop.

The core loop: `REGISTER → MONITOR → OBSERVE → DETECT → UNDERSTAND → CREATE ISSUE → CREATE TASK → TAKE ACTION → MONITOR RESULT → RESOLVE → LEARN/PREDICT → RECOMMEND NEXT ACTION`.

## 7. Asset layer — *what exists?*

Trees, plants, crops, batches, fields, zones, gardens/orchards, species. Hierarchy:

```
Organization → Workspace → Project → Location (Field | Zone) → Planting → Batch → Biological Asset
```

- **Individual asset** (a tree with a tag, GPS point, species) for Green mode and high-value crops.
- **Batch / population asset** (e.g. "Tomato Batch #17, ~84,200 plants, Field 3") for Agri mode, where tracking individuals is infeasible. A batch is a first-class asset with `estimated_count` and sampled observations; individual plants may optionally be registered inside it.
- Species/crop catalog (global seed + workspace custom) carries lifecycle template, expected durations, and agronomic parameters.

## 8. Operations layer — *what needs to happen?*

Tasks (water, fertilize, inspect, treat, prune, plant, replace, harvest, monitor) with assignee, due date, priority, status, history; Inspections (scheduled/ad-hoc observation templates); Treatments (recorded interventions linked to issues); Irrigation events; Planting and Harvest records. All operations link back to an asset, location and (where relevant) an issue.

## 9. Intelligence layer — *what should happen next?*

Layered and honest about provenance: **RULE → STATISTICAL → MODEL → LLM → PREDICTION → RECOMMENDATION** (see §24 and [AI_ARCHITECTURE](AI_ARCHITECTURE.md)). Every output carries `method`, `inputs`, `explanation`, and `uncertainty` where applicable. MVP ships rules and simple statistics only.

## 10. Botanical Operations Agent

A background evaluator (not a chatbot) that continuously answers *"what requires attention?"* and translates it into **Recommendations** that a human can accept → creating an Issue/Task. MVP: a deterministic rules engine.

MVP rule catalog (all explainable, thresholds configurable per workspace):

| Rule | Trigger | Output |
|---|---|---|
| `inspection_gap` | `now − last_observation > N days` (default 21) | Recommend inspection task |
| `health_decline` | health score dropped ≥ X points over 14 d | Recommend issue + inspection |
| `critical_health` | health < critical threshold | Recommend issue (high severity) |
| `symptom_cluster` | ≥ K assets in a zone/batch with same symptom tag within W days | Recommend issue (cluster) |
| `overdue_task` | task past due | Escalate / surface |
| `harvest_window_entry` | batch age/stage enters configured window | Recommend harvest task (*rule on stage duration, labelled as such, not a prediction*) |
| `irrigation_defer` | forecast rain ≥ R mm and last soil moisture ≥ M | Recommend postponing irrigation (needs weather provider) |
| `canopy_decline` | zone canopy measure drops > X% over 90 d (when canopy data exists) | Recommend inspection |

Recommendation lifecycle: `OPEN → ACCEPTED (→ entity created) | DISMISSED (reason) | EXPIRED`. Deduplicated by `(rule, subject, window)` so users are not spammed.

## 11. MVP scope

See [MVP_SCOPE](MVP_SCOPE.md). Summary: workspaces & mode, asset registry with lifecycle, observations/health/growth history, tasks, issues (first-class with workflow & history), map with layers, mode-specific dashboards, rules-based agent, reports from real data, auth & workspace isolation, and **frontend surfaces for every future intelligence feature, clearly marked "Coming soon"**.

## 12. Future features

Crop recommendation, disease detection (CV), growth/survival/yield/harvest prediction, irrigation optimization, profitability forecasting, canopy estimation, LLM natural-language query & report generation, optimization of maintenance resources. See §25–34 and [FUTURE_ROADMAP](FUTURE_ROADMAP.md).

## 13. Frontend experience

Serious operational software: dense but uncluttered, strong status language, map + data integration, explainable AI, uncertainty bands, mobile-friendly field workflows, accessible, responsive. **Not** a generic AI-SaaS dashboard: biological/operational context (lifecycle chips, species, zone, health spectrum, season) is visible everywhere. Details: [FRONTEND_ARCHITECTURE](FRONTEND_ARCHITECTURE.md), [UX_FLOWS](UX_FLOWS.md).

Rules for future-feature surfaces: real layout, real form controls (disabled where backend absent), a visible `Coming soon` / capability badge naming the technique ("Computer vision"), empty states, **no fabricated outputs presented as real**. Any demo data is isolated behind an explicit dev-only flag and watermarked "Sample data".

## 14. User journeys

**Agriculture:** create farm workspace → add location → create fields → pick crop (manual in MVP; recommended later) → create crop batch → register estimated population/plants → monitor health → record observations → agent flags anomaly → issue → task → worker acts → recheck → (later: growth/yield/harvest prediction) → harvest → revenue/profit.

**Green management:** create green space → define zones → register trees → map assets → health inspections → issues → maintenance tasks → interventions → survival monitoring → canopy monitoring → coverage/impact reporting.

**Field worker (mobile):** open "My tasks" → open task → navigate to asset on map → log observation (health picker, tags, photo, note) → complete task. Works with flaky connectivity (queued writes — V2 for full offline; MVP: resilient retry + draft persistence).

## 15. Feature-by-feature workflows

1. **Onboarding:** sign up → create organization → create workspace (select mode) → guided first project/location → import or add first assets.
2. **Register asset:** choose species/crop → place on map or enter coordinates → set lifecycle stage & planting date → optional photo/tag → asset profile created with initial `LifecycleEvent` and (optional) initial observation.
3. **Observe:** from asset, batch or task → structured form (health score/category, growth metrics, symptom tags, notes, photos, env readings) → append-only `Observation` → derived `HealthRecord`/`GrowthRecord` → triggers rule evaluation.
4. **Issue:** from observation, recommendation, or manually → fields (asset/location, category, severity, evidence, assignee) → workflow transitions with history → linked tasks → resolution (with verification observation).
5. **Task:** create (manual/from issue/from recommendation/recurring inspection) → assign → in progress → done (+ optional observation) → verification when linked to an issue.
6. **Recommendation:** agent run → list in "Attention" inbox with explanation → accept (creates entity) or dismiss (reason; feeds suppression).
7. **Report:** pick template → parameters (project, period) → generated from records → view/export (CSV in MVP; PDF V2).

## 16. Information architecture

```
Home (Attention inbox + KPIs)
Workspace switcher
Assets       All · Trees · Plants · Crops · Batches · Species · Locations (Fields/Zones)
Work         Tasks · Issues · Inspections · Harvests
Monitor      Health · Growth · Yield* · Weather* · Irrigation* · Map
AI           Botanical Operations Agent · Crop Recommendation* · Disease Detection* ·
             Growth Prediction* · Survival Prediction* · Yield Prediction* · Harvest Prediction*
Reports      Analytics · Impact · Financials*
Settings     Workspace · Members · Thresholds/Rules · Species catalog · Integrations
```
`*` = future surface (Coming soon). Navigation is **mode-aware**: Green mode hides Harvests/Financials emphasis, Agri mode foregrounds Yield/Harvest. Capability flags per workspace decide enabled/"coming soon" state.

## 17. Domain model

See [DOMAIN_MODEL](DOMAIN_MODEL.md). Principles: reusable entities (no per-screen duplicates), polymorphic asset kinds via one `asset` table with `kind` discriminator, **append-only time series** for state, status-history tables for every workflow, workspace-scoped everything.

## 18. Core entities

User, Organization, Membership, Workspace, Project, Location (Field/Zone, hierarchical, PostGIS geometry), Species/Crop, BiologicalAsset (individual or batch), Planting, LifecycleEvent, Observation, HealthRecord, GrowthRecord, EnvironmentReading/WeatherRecord, Issue + IssueStatusHistory, Task + TaskStatusHistory, Inspection, Treatment, Harvest, Recommendation, Prediction (reserved), Report, Attachment. Full field-level spec in [DATABASE_SCHEMA](DATABASE_SCHEMA.md).

## 19. Lifecycle model

Lifecycle is **data, not code**: a `LifecycleTemplate` (per mode and per species/crop) defines ordered stages, allowed transitions, and typical durations. Assets store `current_stage` plus an append-only `LifecycleEvent` log (`stage, entered_at, source, note`). Terminal/exception stages exist in both modes: `DEAD`, `REMOVED`, `REPLACED` (and `FAILED` for batches). Stage durations feed the rule-based `harvest_window_entry` and, later, predictions.

## 20. Issue system (signature feature)

Issues are first-class domain objects, not tickets with botanical labels.

- **Fields:** `key` (`GG-001`, per workspace), title, description, category (disease, pest, nutrient, water stress, irrigation failure, physical damage, growth anomaly, harvest readiness, maintenance, other), severity (low/medium/high/critical), subject (asset or location or batch — polymorphic), location, evidence (observations + attachments), responsible user, lifecycle state, source (`manual|observation|agent|model`), resolution (outcome, notes, verified_by/at), timestamps.
- **Workflow templates by category class** (configurable data):
  - Plant health: `OPEN → INVESTIGATING → TREATMENT → MONITORING → RESOLVED`
  - Field disease: `OPEN → FIELD_INSPECTION → TREATMENT → MONITORING → RESOLVED`
  - Infrastructure: `OPEN → ASSIGNED → FIXED → VERIFIED`
  - Harvest readiness: `PENDING → INSPECTION → READY → HARVESTED`
  - Always reachable: `CLOSED_WONT_FIX`, and reopen from `RESOLVED`.
- Every transition writes `IssueStatusHistory` (actor, from, to, note, at). Transitions are validated server-side against the template.
- Issues own/aggregate Tasks; resolving requires no open blocking tasks (override with reason). Resolution encourages a verification observation (closes the *"did it work?"* loop).
- Cluster issues link many assets (`issue_asset` association) — e.g. 14 plants in Zone B.

## 21. Task system

Fields: key, title, type (water, fertilize, inspect, treat, prune, plant, replace, harvest, monitor, other), subject (asset/location/batch), issue link, assignee, due date, priority (P1–P4), status (`TODO → IN_PROGRESS → DONE | CANCELLED`, `BLOCKED` optional), source (`manual|issue|agent|schedule`), completion notes, optional resulting observation. `TaskStatusHistory` append-only. Recurrence (inspection schedules) via `RecurrenceRule` generating tasks idempotently. "My tasks" view is mobile-first.

## 22. Map

Layered map (MapLibre GL, vector tiles/raster basemap configurable). Data via GeoJSON from `/map`, bbox-filtered, clustered at low zoom. MVP layers: **Assets, Health (color ramp), Issues, Tasks, Boundaries (fields/zones)**. Reserved, disabled-with-badge layers: Disease hotspots, Soil moisture, Irrigation, Growth, Canopy, Survival risk, Yield. Layer registry is data-driven so new layers do not require map rewrites. Draw/edit tools for boundaries and points.

## 23. Dashboards

**Green:** Trees, Healthy, At Risk, Critical, Survival %, Canopy %, Coverage, Open Issues, Open Tasks, Attention inbox, health distribution, inspection-gap list. Survival/Canopy show real values only when computable from records (survival = alive/(planted); canopy only if measured) otherwise "Not enough data".
**Agri:** Plants (estimated), Health, Growth, Flowering %, Fruit set %, Open Issues/Tasks, upcoming harvest tasks. Yield/Harvest/Revenue **estimates** appear as `Coming soon` until a real model exists; no number is shown that wasn't computed.

Health bands (configurable): Healthy ≥ 70, At Risk 40–69, Critical < 40 — derived from the latest `HealthRecord`.

## 24. AI/ML roadmap

| Phase | Capability | Method |
|---|---|---|
| MVP | Attention rules, inspection gaps, threshold health alerts, symptom clustering, simple trend (linear slope) detection | RULE / STATISTICAL |
| V2 | Disease detection from images; survival & growth forecasting (baseline stats → ML); irrigation recommendations (weather + soil); LLM explanation & NL query over structured data | CV, ML, LLM |
| V3 | Yield/harvest prediction, crop recommendation, profitability, canopy estimation (satellite/CV), optimization of maintenance & irrigation | ML + optimization |

Principles: never claim a capability not implemented; separate RULE/MODEL/LLM/PREDICTION/RECOMMENDATION; expose uncertainty; log model versions; predictions are stored with inputs & version so they can be back-tested against outcomes.

## 25. Crop recommendation (V3; surface in MVP)

Inputs: location, area, soil type, pH, water availability, season, target market, budget. Outputs: ranked crops with suitability, expected yield range, revenue/profit ranges, risk, and an explanation; action **Start Project** (creates project + batch). Needs: agronomic knowledge base, soil/weather data, market price source. MVP: page with form + `Coming soon`, form state not submitted.

## 26. Disease detection (V2; surface in MVP)

Flow: select asset → upload image → model inference → result (condition, confidence, severity, affected area %) → **creates Observation** → user may **Create Issue** → task. Needs: labelled dataset or vetted pretrained model, upload validation, model registry. Always shows confidence and "not a diagnosis" guidance; low-confidence results route to human review.

## 27. Growth prediction (V2)

Asset page growth panel: current %, history chart, forecast band, expected maturity with range, confidence. Baseline = species lifecycle template + observed growth curve fit; ML when enough data. Uncertainty shown as bands, never single-point false precision.

## 28. Survival prediction (V2)

Tree-level 90-day survival probability + categorical risk + ranked risk factors (water stress, heat exposure, disease, inspection gap). Feeds task prioritization. Early version = transparent weighted risk score (labelled RULE), later calibrated model.

## 29. Irrigation intelligence (V2)

Inputs: soil moisture, forecast, crop & stage, area. Output: recommended volume/time window, potential saving, **Create Irrigation Task**. Phase 1 = rule-based water balance with evapotranspiration estimate; Phase 2 = learned.

## 30. Yield prediction (V3)

Range + confidence + trend, updating as observations arrive. Requires several seasons of the user's own data or a validated crop model; until then not shown.

## 31. Harvest prediction (V3)

Readiness %, predicted window range, links to **Create Harvest Plan** → tasks/Harvest record. MVP provides stage-duration *rule* ("entered harvest window") only.

## 32. Revenue / profitability (V3)

Expected price range × yield range − cost; costs captured from task/treatment cost fields (MVP captures cost data so V3 has ground truth). Ranges, not point estimates.

## 33. Green-management analytics

Survival rate, health distribution over time, growth, canopy (when measured), coverage by zone, intervention effectiveness, inspection compliance; later projected canopy/survival and intervention prioritization under resource constraints.

## 34. Reporting

Reports are **generated from underlying records**, never manually keyed metrics. Green: plantation → survival → health → growth → canopy → coverage → impact. Agri: planting → health → growth → yield → harvest → revenue → profitability. MVP: Analytics + Impact basic reports (CSV export), Financials as surface. V2: PDF with charts, scheduled delivery.

## 35. Security

- AuthN: email+password (argon2id) with short-lived JWT access + rotating refresh tokens; designed behind an interface for OIDC/SSO swap.
- AuthZ: workspace-scoped RBAC (`owner`, `admin`, `manager`, `worker`, `viewer`); every query filtered by `workspace_id` through a single dependency; negative cross-tenant tests mandatory.
- Uploads: type/size allow-list, magic-byte check, EXIF GPS handling (strip or retain by policy), virus-scan hook, private bucket + signed URLs.
- Secrets in env only; `.env.example` lists names; no secrets in repo/logs.
- Input validation via Pydantic; parameterized SQL only; rate limiting on auth; CORS allow-list; audit log of status transitions (already in history tables).
- PII minimal (name, email, phone optional); data export/deletion path (V2).

## 36. Scalability

Target: single workspace 1M assets (municipal), 10M observations. Strategies: BRIN/btree indexes on time-series, composite `(workspace_id, …)` indexes, GiST on geometries, partitioning of `observation`/`health_record` by time when > ~50M rows, materialized/rollup tables for dashboards (`asset_state` current-state projection), bbox + clustering for map, pagination (keyset) everywhere, async/background jobs for agent runs and reports, stateless API behind a load balancer.

## 37. Non-functional requirements

| Area | Requirement |
|---|---|
| Performance | p95 API < 300 ms for list/detail at 100k assets; dashboard < 1 s via projections; map first paint < 2 s |
| Availability | 99.5% MVP target; graceful degradation when weather/AI providers fail |
| Data integrity | FK + CHECK constraints; append-only time series; no destructive overwrite of state; soft-delete for assets |
| Accessibility | WCAG 2.1 AA: keyboard nav, contrast, non-color-only status encoding |
| Responsive | Usable at 360 px width; field workflows touch-first |
| i18n | English first; string externalization from day one (Hindi/Marathi V2) |
| Observability | Structured logs, request IDs, error tracking, job-run records for the agent |
| Testability | Unit (rules, workflow), API (tenant isolation), integration (DB), critical frontend flows |
| Portability | Containerized; runs on a single VM or managed services |

## 38. MVP vs V2 vs V3 vs V4

Evolution: **MVP operational foundation → V2 Prediction → V3 Recommendation → V4 Optimization** (ADR-012).

| | MVP | V2 Prediction | V3 Recommendation | V4 Optimization |
|---|---|---|---|---|
| Workspaces, modes, RBAC | ✔ | SSO, org-level roles | | Multi-org enterprise |
| Assets, lifecycle | ✔ | Bulk import, QR tags | Canopy estimation | Drone/satellite ingestion |
| Observations, photos | ✔ | Offline-first PWA sync | | IoT sensor streams |
| Issues & tasks | ✔ | Recurring schedules, SLAs, notifications | | Crew allocation |
| Map | ✔ core layers | Intelligence layers live | | Time-slider, 3D canopy |
| Agent | ✔ rules | Prediction-aware rules | + LLM explanations, NL query | Cross-module planner |
| Disease detection | surface | ✔ | | Per-crop fine-tuning |
| Growth / survival | surface | ✔ | | Calibrated per species |
| Yield / harvest prediction | surface | ✔ (needs history) | | |
| Irrigation | surface (rule: defer on rain) | | ✔ recommendation | ✔ optimizer |
| Crop recommendation | surface | | ✔ | Crop-mix optimization |
| Profitability | surface | | ✔ ranges | Profit optimization |
| Reports | basic + CSV | PDF, scheduled | Narratives | Custom builder, ESG/CSR |

## 39. Risks

| Risk | Mitigation |
|---|---|
| Scope explosion from the vision | Strict MVP scope; future = surfaces only; feature flags |
| Over-claiming AI | Provenance labels; no mock predictions in prod; review checklist in DEVELOPMENT_GUIDELINES |
| Data model too rigid/too loose (individual vs batch) | Single asset table + `tracking_mode`; ADR in DECISION_LOG |
| PostGIS/DB ops complexity for small teams | Managed Postgres with PostGIS; docker-compose for dev |
| Poor field connectivity | Small payloads, retry queue, PWA; offline sync V2 |
| Cold-start (no data → no intelligence) | Rules need little data; strong import path; capture-for-future-ML from day one |
| Multi-tenant data leak | Central scoping dependency + mandatory isolation tests |
| Image/disease-model liability | "Decision support" framing, confidence + human review |

## 40. Recommended technology stack

Greenfield repository → adopt the recommended stack (rationale in [DECISION_LOG](DECISION_LOG.md) ADR-001..):

- **Frontend:** React 18 + TypeScript + Vite, Tailwind CSS, shadcn/ui (Radix), React Router, TanStack Query, react-hook-form + zod, Recharts, MapLibre GL JS, i18next.
- **Backend:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.0 (typed), Alembic, GeoAlchemy2, structlog, pytest.
- **Data:** PostgreSQL 16 + PostGIS 3.
- **Jobs:** MVP — DB-backed job table + APScheduler worker process (no Redis); path to Celery/RQ + Redis in V2 when load requires.
- **Storage:** S3-compatible (MinIO local, S3/R2 prod) via abstraction.
- **Auth:** first-party JWT now, OIDC-ready interface.
- **AI:** none required for MVP; `intelligence/` package with provider interfaces; scikit-learn/PyTorch/OpenCV/LLM API added only with a real model.
- **Infra:** Docker, docker-compose (dev), GitHub Actions CI.

## 41. Recommended architecture

Modular monolith (API + worker sharing one codebase) with domain modules (`assets`, `observations`, `issues`, `tasks`, `intelligence`, `reports`, …), layered `router → service → repository`. Detail in [ARCHITECTURE](ARCHITECTURE.md). Split services (ML inference) only when independently scaled.

## 42. Deployment considerations

Containers for `web` (static, CDN), `api`, `worker`; managed Postgres+PostGIS; object storage; env-based config (12-factor); migrations run as a release step; health endpoints; staging + prod; backups (PITR) for DB; weather provider keys via secrets; basemap tiles provider key/config.

## 43. Testing strategy

- **Unit:** rules engine (table-driven), workflow transitions, health-band computation, lifecycle validation.
- **API/integration:** against real Postgres/PostGIS (test containers or CI service); tenant isolation; auth flows; pagination; map bbox queries.
- **Contract:** OpenAPI snapshot; generated TS client type-check in CI.
- **Frontend:** component tests (Vitest + Testing Library) for forms/workflows; Playwright smoke for golden path (register asset → observe → agent recommends → accept → task → complete → issue resolved).
- **Non-functional:** seed-scale perf test (100k assets) in CI nightly; accessibility checks (axe).
- No tests merely for coverage numbers.

## 44. Future extensibility

- **Pluggable intelligence:** `Detector`, `Predictor`, `Recommender` interfaces; registry with model versions; all outputs persisted as `Observation`/`Prediction`/`Recommendation` with provenance.
- **Pluggable data sources:** weather, soil, satellite, IoT through `Provider` interfaces and `EnvironmentReading` ingestion.
- **Map layer registry**, **lifecycle templates**, **workflow templates**, **report templates**, **species catalog** are data → extend without code forks.
- **Domain events** (`observation.created`, `issue.transitioned`, …) via an in-process bus now, outbox → queue later, enabling webhooks and integrations.
- **API versioning** (`/api/v1`) with additive evolution.
