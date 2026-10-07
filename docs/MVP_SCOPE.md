# MVP Scope

Goal: establish the operational foundation (register → observe → detect → issue → task → verify) with rules-based intelligence and a UI that already anticipates future intelligence.

## In scope
| Area | Included |
|---|---|
| Identity | Register/login, orgs, workspaces, RBAC (owner/admin/manager/worker/viewer), tenant isolation |
| Workspace | Create, select mode, settings, rule thresholds |
| Structure | Projects, locations (site/field/zone/plot) with polygons |
| Catalog | Seed species/crops + lifecycle templates (both modes), custom species |
| Assets | Individual + population (batch) assets, profiles, lifecycle events, archive |
| Monitoring | Observations (health, growth, symptoms, notes, photos, env readings), time-series charts, `asset_state` projection |
| Issues | Create (manual/from observation/from recommendation), severity, category, evidence, assignment, workflow templates, history, resolution |
| Tasks | CRUD, assignment, due dates, priority, status workflow, history, link to issue/asset, recurring inspections, treatments/irrigation/planting/harvest records |
| Map | Assets, health, issues, tasks, boundaries layers; draw points/polygons; layer registry incl. disabled future layers |
| Dashboards | Green + Agri, computed-only KPIs with "not enough data" states |
| Agent | Rules engine (PRD §10), recommendation inbox (accept/dismiss), run history, rule settings |
| Weather | Provider interface + one provider for observed/forecast; used by `irrigation_defer` rule |
| Reports | Analytics + Impact basic from records, CSV export |
| Future surfaces | Crop Recommendation, Disease Detection, Growth/Survival/Yield/Harvest Prediction, Irrigation, Financials — real layouts, `Coming soon` |
| Platform | OpenAPI, migrations, CI, Docker, tests, docs |

## Explicitly out of scope (MVP)
Any ML/CV model, LLM features, crop recommendation engine, predictions of any kind, full offline sync, bulk import UI (API stub only), PDF reports, notifications (email/push/WhatsApp), SSO, billing, multi-org enterprise admin, satellite/drone/IoT ingestion, native mobile apps.

## Definition of Done (per feature)
Backend endpoint + validation + error handling + tenant scoping tests · migration · frontend with loading/empty/error/forbidden states · responsive + keyboard accessible · unit/API tests for business rules · docs updated (CURRENT_STATE, API/DB docs, DECISION_LOG if architectural).

## Build order (vertical slices)
0. Scaffold & infra (repo, CI, docker-compose, base app shells, auth skeleton)
1. Identity + workspaces + RBAC + tenant isolation tests
2. Locations + catalog + assets (+ lifecycle) + asset list/profile
3. Observations + health/growth records + `asset_state` projection + charts
4. Issues (workflow engine) + tasks (+ history) + linking
5. Agent rules engine + recommendations inbox + job runner
6. Map + dashboards (both modes)
7. Reports + weather + future-surface pages + polish/accessibility
8. Hardening: perf seed test (100k), e2e golden path, security pass

## Acceptance (MVP exit)
Golden path passes in Playwright for both modes: register asset → record declining observations → agent recommends → accept → task assigned → worker completes with observation → issue resolved with verification → dashboard KPIs and report reflect it. Cross-tenant isolation tests green. No UI element shows an unimplemented intelligence output as real.

## Status against the build order (2026-10-07)

| Step | Status |
|---|---|
| 0 Scaffold, CI, DB baseline | done (CI written and linted; first GitHub run pending) |
| 1 Identity, workspaces, RBAC, tenant tests | done |
| 2 Locations, catalog, assets | done (lifecycle events/templates, bulk import: not yet) |
| 3 Observations, state projection | done (charts, photo upload, environment readings: not yet) |
| 4 Issues + tasks | done (recurring tasks, treatments, harvest records: not yet) |
| 5 Agent | done for 3 rules + recommendations; weather rules and worker/scheduler: not yet |
| 6 Map + dashboards | not started (Home shows counts) |
| 7 Reports, surfaces, polish | surfaces done earlier; reports not started |
| 8 Hardening | partially (RLS, immutability, CI); e2e on CI and perf seed pending |
