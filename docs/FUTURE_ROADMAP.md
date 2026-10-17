# Future Roadmap

## Living roadmap: stages A-N (dependency-aware; status as of 2026-10-17)

Legend: done / in progress / next / later. A stage is "done" only when its acceptance criteria are verified.

| Stage | Scope | Depends on | Status |
|---|---|---|---|
| A Engineering foundation | auth hardening (throttling, verification, reset), request IDs, audit log, Dockerfiles, deployment and backup/restore docs | none | **mostly done**: CI, RLS, migrations, tenancy, throttling, request IDs, audit trail done (A2, 2026-10-17); open: verification/reset, Dockerfiles, deployment and backup docs |
| B Core operations | assets, observations, issues, tasks, dashboard, map, **evidence (photos)**; still open: inspections and treatments as first-class records, reports, species lifecycle | A (mostly done) | **mostly done**; evidence landed 2026-10-17 |
| C Botanical Operations Agent | scheduled evaluation, rule configuration and versioning, `irrigation_defer`, outcome verification, execution tracking | B | **partial**: rules and manual runs exist; scheduler next |
| D Data and ML foundations | dataset catalog and licences, labelling workflow, versioned splits, evaluation harness, data-quality checks | B (evidence), C | **next after C starts**; needs real labelled data decisions |
| E Disease detection | image to candidate condition with confidence, human review, issue and task | D, evidence | later; **not started, no model, no dataset** |
| F Growth prediction | baselines first, then models | D (history) | later |
| G Survival and risk | calibrated probabilities, survival analysis | D, F | later |
| H Crop recommendation | agronomic suitability, then economics | D, soil/climate data | later |
| I Irrigation intelligence | advisory rule, then water-demand estimate, then optimisation | C, weather, soil data | later |
| J Yield prediction | transparent baselines, then models with intervals | D, F | later |
| K Harvest prediction | window, readiness, confirmed readiness, outcome | J | later |
| L Canopy, coverage, environmental intelligence | needs imagery and validation data | D | later |
| M Financial and resource optimisation | needs real cost and price inputs | H, I, J | later |
| N Reporting, integrations, production readiness | exports, notifications, monitoring, security review | all | ongoing |

Rule for every stage: working software, tests, documentation and a written technical explanation before the next stage; no stage claims a model that was not trained and evaluated.

## Product evolution (ADR-012; matches the Stage-2 deck)

```
MVP  Operational foundation   →   V2  Prediction   →   V3  Recommendation   →   V4  Optimization
```

Ordering reflects dependency on data and platform maturity, not calendar commitments. Every stage needs real recorded data; the MVP therefore captures time-stamped observations, treatments, costs and outcomes from day one.

## V2 — Prediction (what will happen?)
- **Disease detection** (computer vision): vetted pretrained model first, per-crop fine-tuning later; image → model → Observation → Issue → Task; human review for low confidence.
- **Growth and survival prediction:** baseline statistical → ML once enough outcomes exist; forecast bands in the UI; survival feeds task priority.
- **Yield and harvest prediction:** only once enough of the user's own history (or a validated crop model) exists; ranges with confidence, never point values.
- **Field operations:** PWA offline sync, QR tag scanning, bulk import (CSV/KML/GeoJSON), notifications (email/WhatsApp/push), recurring schedules and SLAs.
- **Platform:** Celery/RQ + Redis workers, SSO/OIDC, i18n (Hindi/Marathi), time-partitioned history tables, PDF reports.

## V3 — Recommendation (what should we do?)
- **Crop recommendation:** soil + weather + location + water + season + market → ranked crops with suitability, expected yield range, cost and profit range, risk, explanation. "Start Project" creates the project and batch.
- **Irrigation recommendation:** water balance from weather, soil moisture, crop and growth stage → recommended volume/time → Create Irrigation Task.
- **Profitability:** yield range × price range − cost (costs captured from task/treatment records since the MVP).
- **LLM layer:** grounded explanations of recommendations/predictions, natural-language questions over the structured API, report narratives.
- **Canopy estimation** (satellite/drone/CV) and canopy projection.

## V4 — Optimization (how should the whole operation run?)
Given land, water, labour, weather, crop economics and risk constraints, determine the best operating strategy: irrigation optimization, maintenance-crew allocation, intervention prioritization with predicted survival uplift, crop-mix/profit optimization. Plus IoT/sensor ingestion, 3D/time-slider map, enterprise multi-org administration, public API and webhooks.

## Standing technical investments
Model registry and back-testing against outcomes; feature store derived from history tables; data-quality dashboards; load testing at municipal scale (1M assets); cost controls for imagery/LLM.

## Open product questions (to resolve with users)
1. Default health scoring: numeric 0–100 vs categorical field input — which do field workers actually use?
2. Survival definition per organization (alive at 90 d? 1 yr?) — configurable.
3. Population batches: how often are individual plants registered inside batches in practice?
4. Preferred notification channel for workers (WhatsApp vs SMS vs app).
5. Basemap/imagery provider and licensing for production.
