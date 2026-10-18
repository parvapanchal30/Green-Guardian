# Current State

_Last reconciled with the repository: 2026-10-18. Verified against code, tests and the GitHub Actions run, not against older docs._

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
| Audit log page (filters, pagination, request IDs, escaped details, role-gated nav) and `/audit/meta` | V | 9 frontend tests, checked in a browser; server enforces manager/owner and workspace scope |
| Audit retention (configurable, 30-day floor enforced by a PostgreSQL trigger, purge is itself audited) | V | `test_audit_retention` (PostgreSQL trigger test included), ADR-035; run daily by the Stage C worker (and by `python -m app.tools.housekeeping`); the worker is verified as a process, a real deployment is not |
| Access-denied (403) events | V | `test_access_denied` (mutation-checked), ADR-036 |
| Container images and compose stack | V | CI job `containers`: hadolint, Trivy scan, `ops/smoke-compose.sh` (29 checks); **not run on a developer machine (no Docker installed)** |
| Backup and restore tooling | V / I | CI job `backup-restore` proves dump, restore into a scratch PostGIS 17 database, manifest verification and the safeguards; **a backup of the real Supabase database has not been taken** (client tools not installed) (I) |
| Dependency vulnerability audit | V | CI job `supply-chain` (pip-audit, npm audit): clean |
| Workspaces, roles (viewer/worker/manager/owner), mode selection | V | `test_tenancy` matrix: every `{ws}` route must be listed and isolation-tested |
| Row-Level Security, composite tenant FKs, append-only history triggers | V | migrations 0002/0004; `test_postgis`, `test_db_integrity` on PostgreSQL |
| Locations (PostGIS centroid), species catalog, assets, `asset_states` projection | V | `test_assets_api`, `test_postgis` |
| Observations (append-only), health bands | V | `test_observations_api` |
| Botanical issues (workflow, history, evidence, resolution) | V | `test_issues_api` |
| Tasks (workflow, assignment, follow-up observation) | V | `test_tasks_api` |
| Rule-based agent: `critical_health`, `health_decline`, `inspection_gap` (v2), de-duplication, dismissal suppression | V | `test_mvp_rules`, `test_agent_api`, `test_agent_outcomes` |
| **Scheduled agent worker** (`python -m app.worker`): per-workspace schedule, retries with backoff, run history, no overlapping runs, abandoned-run recovery, graceful shutdown, heartbeat health check | V | ADR-039; `test_scheduler` (16), `test_agent_runs` (13), `test_worker` (6), `test_worker_process` (3: a real subprocess, signal, exit 0); compose service `worker` + smoke checks run by CI; **not run in Docker locally** |
| **`irrigation_defer`** (advisory, forecast-based; never uses soil moisture as a trigger; withheld on water-stress signs; lists what is not known) | V (logic) / P (agronomy) | ADR-040; `test_irrigation_rule` (10), `test_irrigation_flow` (16), fake weather provider, no live calls. **Thresholds are conservative defaults, not validated against irrigation records or sensors (none exist)** |
| Recommendation lifecycle: run and rule-version traceability, structured evidence, expiry, outcomes (task completed/cancelled, issue resolved/closed, deferral applied) | V | ADR-041; `test_agent_outcomes` (8); nothing learns from outcomes |
| Agent page: suggestions by status, run history (failures, skipped cases), rule versions, forecast-based advice labelled | V | 6 + 4 frontend tests |
| `symptom_cluster` rule | P | in the rules library, not wired |
| Weather behind provider boundary (Open-Meteo, mock) | V | `test_weather*`, AST boundary test; live path verified manually; free tier is non-commercial (R-WX-1) |
| Dashboard read model (DB aggregates, both modes) | V | `test_dashboard_api`, statement-count test |
| Map read model (PostGIS, layer registry) + Leaflet UI | V / I | `test_map_api` incl. GiST plan test; the UI verified manually in a browser, no automated end-to-end test (I) |
| **Evidence / photo storage** (upload, validation, storage abstraction, gallery) | V | ADR-031; 27 backend tests, 9 frontend tests, real-browser upload; **no thumbnails, no purge job, no cloud storage adapter** (P) |
| Reports, exports, notifications | D | roadmap Stage N |
| Hosting, TLS, log shipping, monitoring and alerts | D | `DEPLOYMENT.md` is a plan; nothing deployed, no provider chosen |
| Error tracking service, metrics | N | structured logs with request IDs only |
| **Stage D data foundations**: dataset catalog with licence policy and approval blockers (images / annotations / image origin / evidence), append-only evidence and approval history, label review workflow (unreviewed, under review, accepted, rejected, corrected) with reviewer, time, change and evidence, quality checks, grouped splits with leakage checker and versions, evaluation metrics, reviewer agreement, claim gate | V (logic, API, database) on **synthetic fixtures only** | ADR-044; `test_dataset_licences` (47), `test_dataset_quality` (19), `test_dataset_splits` (19), `test_dataset_evaluation` (10), `test_dataset_agreement` (7), `test_dataset_worksheet` (8), `test_datasets_api` (41, 6 of them PostgreSQL-only); 16+ routes in the tenancy matrix; migrations 0008 and 0009. **No UI.** |
| Datasets, experiments (Stage E onward) and every model | N | no external dataset is approved or downloaded; no model exists; disease-model training and performance claims are blocked (see DATASETS.md section 6) |

## Verification (what was actually run)
- **CI, Stage D (run 39120030935, head `c737098`): all five jobs succeeded.** Backend: 697 passed, 2 skipped (a SQLite-only tamper test and the opt-in profiler) on PostgreSQL 17 + PostGIS, including the database tests for append-only evidence, reviews and splits, the approver constraint and the cross-tenant foreign key. A first run failed one test that fast mode could not show (the per-process access-denied de-duplication window); fixed in the test.
- **Earlier CI (GitHub Actions, run 39070024954, head `519544b`, Stage C): all five jobs succeeded.**
  - `backend`: ruff, format check, mypy, `alembic upgrade head` to `0007`, `alembic check` (no drift), `check_db`, downgrade to base and upgrade again, the full pytest suite on a PostgreSQL 17 + PostGIS 3.5 container with skipping forbidden (513 passed, 1 skipped: the opt-in profiler), request profile.
  - `frontend`: `npm ci`, type-check, lint, 73 tests, build.
  - `containers`: hadolint on both Dockerfiles; both images built; Trivy found no fixable HIGH/CRITICAL vulnerabilities; the compose smoke test passed 29 checks, five of them new for the worker (healthy heartbeat, a scheduled agent run recorded for a new workspace, the run names its worker, uid 10001, exit 0 on SIGTERM); the others: (migration job exit 0, PostGIS in `extensions`, readiness, SPA and deep-link fallback, security headers, `/api` proxy with request ID, register, login, workspace, located asset, PostGIS map query, photo upload and byte-exact download, files on the volume, API uid 10001, web uid 101, no secrets in image layers, API refuses to start without a signing secret).
  - `backup-restore`: dump, restore into a scratch database, verification of 21 tables' row counts, migration revision, generated PostGIS centroids, RLS on all 20 tables, audit and history triggers, GiST indexes and a spatial query; tampered manifest, corrupted dump, non-scratch target names, same-server restore and an unsafe backup directory are all rejected.
  - `supply-chain`: `pip-audit` and `npm audit` clean.
- **Local, before pushing (Stage C):** backend 487 passed and 27 PostgreSQL-only skipped in SQLite fast mode; ruff, format and mypy clean; frontend 73 tests, type-check, build. Migration 0007 applied to the Supabase dev database (`alembic check`: no drift; `check_db`: RLS on 21/21 tables). On the real Supabase server (throwaway schemas, the canary check intact), PostgreSQL mode: `test_agent_runs` 13, `test_scheduler` 16 and `test_worker` 6, `test_irrigation_flow` 16, `test_agent_outcomes` 8, `test_agent_api` 13, `test_irrigation_rule` 10, `test_mvp_rules` 11, `test_weather_boundary` 11, `test_migrations` 1 all passed (CI later ran the whole suite on PostgreSQL). Mutation checks: seven deliberate breakages of the new code (threshold check, water-stress guard, expiry guard, one-running index, empty-history rule, first-outcome-wins, rollback on failure) were each caught by a test; the rollback one first survived, which exposed a weak test (it was strengthened) and an unfaithful SQLite fast mode (ADR-042). A real worker subprocess was started, ran a scheduled run, wrote its heartbeat and exited 0 on a termination signal. One live read of the weather port with the real Open-Meteo provider returned all the fields the irrigation rule needs (rain, probability, temperature, modelled soil moisture).
- **Not verified:** running the containers on a developer machine (CI did); any real hosting provider or TLS; a backup or restore of the real Supabase database; `age` encryption; the worker under real load or with thousands of workspaces; irrigation advice end to end with a real rainy forecast (tests use a fake provider; the live read happened on a dry forecast); the agronomic validity of the irrigation thresholds (no ground truth exists); anything involving a trained model (none exists).

## Environment notes
Windows dev machine, Python 3.13, Node 24, no Docker and no local PostgreSQL. The dev database is Supabase (PostgreSQL 17, PostGIS 3.3.7 in schema `extensions`, application schema `greenguardian`). Migrations through `0009` (… agent runs, dataset catalog and label review, dataset image origin) are applied to the dev database (`alembic check`: no drift; RLS on 27 of 27 tables). `JWT_SECRET` (32+ characters) is now required outside tests. Evidence files are stored under `backend/var/storage` by default (gitignored).

## Known limitations and defects
- Account recovery: no email verification or password reset (needs an email provider); refresh token in `sessionStorage`.
- Backups: Supabase Free has no provider backups, so our own are the only protection; none has been taken from the real database yet (PostgreSQL 17 client tools needed on a machine you control). Retention and housekeeping now run in the worker, which is not deployed anywhere yet.
- Evidence storage: local directory only; more than one API replica needs a shared volume or the S3 adapter (not built). No thumbnails, no purge job for soft-deleted blobs. EXIF (including GPS) is kept.
- Deployment: no provider chosen, nothing deployed. Behind a reverse proxy `TRUSTED_PROXY_COUNT` must be set, otherwise all clients share one address for throttling and audit.
- Access-denied de-duplication is per process.
- Datasets: no screen yet (API only); there is no confirmed qualified reviewer, so review records are not expert validation and claims stay blocked; no dataset is approved; PlantDoc cannot be approved while its image rights are unestablished (its images were scraped from search engines). The application stores evidence and enforces the policy; it cannot verify that evidence is true.
- Agent: one worker evaluates workspaces one after another (a poll costs two queries however many workspaces exist; add workers or shard before thousands of large workspaces). `agent_runs` and recommendations are not pruned. Irrigation thresholds are unvalidated defaults and the rule has no soil-moisture measurement, observed rainfall, crop water requirement or irrigation-volume input; with Open-Meteo's free tier the worker's weather use is non-commercial only (R-WX-1). `symptom_cluster` is still not wired. Outcomes are recorded but nothing learns from them.
- Map tiles use the public OpenStreetMap server (light use only): set `VITE_MAP_TILE_URL` and extend the CSP before production.
- GitHub Actions are pinned by tag, not commit SHA.
- Demo data and credentials used for screenshots live only in `pitch/_work` (gitignored) and a throwaway SQLite file.

## Decisions
ADR-001 to ADR-044 in `DECISION_LOG.md`.

## Must-not-break
Tenant scoping on every query and an isolation test for every route; append-only history; honest AI labelling (no mock predictions, `CapabilityGate` for future features); no secrets in Git; no AI attribution in commits.
