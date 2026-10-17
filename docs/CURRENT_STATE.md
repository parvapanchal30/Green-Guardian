# Current State

_Last reconciled with the repository: 2026-10-17. Verified against code, tests and the GitHub Actions run, not against older docs._

## Where the project is
GreenGuardian has a working operational core for both operating modes (Green Management and Agricultural Production share one model): register assets, record observations, get rule-based suggestions, turn them into issues and tasks, follow them to resolution, see the state on a dashboard and a map, and keep photo evidence. **No machine-learning model exists yet**; the agent is rules and statistics only, and every future intelligence surface is shown as "Coming soon".

Repository: `parvapanchal30/Green-Guardian`, working branch `ci/first-run` (not merged to `main`; nothing has been pushed to `main`).

## Status by capability
Legend: **V** implemented and verified · **I** implemented, verification incomplete · **P** partial · **D** designed, not built · **N** not yet designed.

| Area | Status | Evidence / notes |
|---|---|---|
| Identity: register, login, rotating refresh tokens, argon2id | V | `test_auth`; email verification and password reset **not built** (P) |
| Login/refresh/register throttling | V | `test_login_throttle` (16 tests incl. mutation-checked), ADR-032 |
| Request correlation IDs (header, errors, logs, audit) | V | `test_request_id`, checked live on the dev backend, ADR-033 |
| Audit trail (append-only, recorded in the business transaction, manager read API) | V | `test_audit_trail`; PostgreSQL trigger test; ADR-034 |
| Workspaces, roles (viewer/worker/manager/owner), mode selection | V | `test_tenancy` matrix: every `{ws}` route must be listed and isolation-tested |
| Row-Level Security, composite tenant FKs, append-only history triggers | V | migrations 0002/0004; `test_postgis`, `test_db_integrity` on PostgreSQL |
| Locations (PostGIS centroid), species catalog, assets, `asset_states` projection | V | `test_assets_api`, `test_postgis` |
| Observations (append-only), health bands | V | `test_observations_api` |
| Botanical issues (workflow, history, evidence, resolution) | V | `test_issues_api` |
| Tasks (workflow, assignment, follow-up observation) | V | `test_tasks_api` |
| Rule-based agent: `critical_health`, `health_decline`, `inspection_gap`, de-duplication, dismissal suppression | V | `test_mvp_rules`, `test_agent_api`; manual "Run checks" only, **no scheduler** (P) |
| `symptom_cluster` rule | P | in the rules library, not wired |
| Weather behind provider boundary (Open-Meteo, mock) | V | `test_weather*`, AST boundary test; live path verified manually; free tier is non-commercial (R-WX-1) |
| Dashboard read model (DB aggregates, both modes) | V | `test_dashboard_api`, statement-count test |
| Map read model (PostGIS, layer registry) + Leaflet UI | V / I | `test_map_api` incl. GiST plan test; the UI verified manually in a browser, no automated end-to-end test (I) |
| **Evidence / photo storage** (upload, validation, storage abstraction, gallery) | V | ADR-031; 27 backend tests, 9 frontend tests, real-browser upload; **no thumbnails, no purge job, no cloud storage adapter** (P) |
| Reports, exports, notifications | D | roadmap Stage N |
| Scheduled worker, `irrigation_defer` rule | D | roadmap Stage C |
| Dockerfiles, deployment, backup/restore procedure | D | roadmap Stage A/N |
| Error tracking service, log shipping, metrics | N | structured logs with request IDs only |
| Datasets, labelling, experiments (Stage D) and every model (E-M) | N | nothing built, no dataset downloaded |

## Verification (what was actually run)
- **CI (GitHub Actions, run 3, head `278e2b9`): success.** Backend job: ruff, format check, mypy, `alembic upgrade head`, `alembic check` (no drift), `check_db`, downgrade to base and upgrade again, full pytest with PostgreSQL tests forbidden to skip, request profile. Frontend job: `npm ci`, tsc, oxlint, vitest, build.
- **Since that run (evidence slice, local):** backend 321 passed, 25 PostgreSQL-only skipped in SQLite fast mode; on PostgreSQL (Supabase throwaway schema) 54 passed for evidence, PostGIS/RLS, DB-integrity and migration suites; frontend 48 tests, type-check, lint, build. **The evidence commit has not yet run in GitHub Actions.**
- Not verified: the full API suite on PostgreSQL after migration 0004 in CI; production deployment (none exists); anything involving a trained model (none exists).

## Environment notes
Windows dev machine, Python 3.13, Node 24, no Docker and no local PostgreSQL. The dev database is Supabase (PostgreSQL 17, PostGIS 3.3.7 in schema `extensions`, application schema `greenguardian`). Migrations through `0005` (evidence, auth throttle, audit trail) are applied to the dev database. `JWT_SECRET` (32+ characters) is now required outside tests. Evidence files are stored under `backend/var/storage` by default (gitignored).

## Known limitations and defects
- Auth hardening open: email verification, password reset; refresh token in `sessionStorage`.
- Audit: no 403 access-denied events, no retention/export, no UI; no backup/restore documentation yet.
- Behind a reverse proxy `TRUSTED_PROXY_COUNT` must be set, otherwise all clients share one address for throttling and audit.
- Photos are stored as received (EXIF kept for evidence integrity, including any GPS tags); no thumbnails, so galleries load full images (<= 10 MB each).
- Soft-deleted evidence keeps its blob until a purge job exists.
- Map tiles use the public OpenStreetMap server (light use only): set `VITE_MAP_TILE_URL` before production.
- Demo data and credentials used for screenshots live only in `pitch/_work` (gitignored) and a throwaway SQLite file.

## Decisions
ADR-001 to ADR-031 in `DECISION_LOG.md`.

## Must-not-break
Tenant scoping on every query and an isolation test for every route; append-only history; honest AI labelling (no mock predictions, `CapabilityGate` for future features); no secrets in Git; no AI attribution in commits.
