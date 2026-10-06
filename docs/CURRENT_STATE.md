# Current State

_Last updated: 2026-10-07_

## Repository
- GitHub: `parvapanchal30/Green-Guardian` — **was empty** (no commits) at start. Cloned to `D:\college\GreenGuardian`.
- Contents now: `docs/` (project memory + PRD), `pitch/` (Stage-2 review deck + generator), and a small proof of concept: `backend/app/modules/intelligence/rules/` (rules engine) with `backend/tests/` (5 passing tests) and `backend/poc_run.py` (synthetic data run). (superseded: see Implementation below)

## Audit result
| Question | Answer |
|---|---|
| What works? | Nothing to run — greenfield |
| Retain? | N/A |
| Refactor/remove? | N/A |
| Missing? | Everything: backend, frontend, DB, infra, CI, tests |
| Architectural risks | See ARCHITECTURE §14 |

## Environment (dev machine)
Python 3.13.3, Node 24.14.0 present. **Docker not installed.** PostGIS availability is the first setup blocker (ADR-007). Git identity: `parvapanchal30 <parvampanchal.c@gmail.com>`.

## Decisions made
ADR-001..011 in DECISION_LOG.md (stack, monolith, asset model, append-only history, jobs, modes, PostGIS, capability-gated future surfaces, rules-first agent, auth, template-driven workflows).

## Next
See `TODO.md` — Phase 0 scaffold, then vertical slices per MVP_SCOPE build order.

## Must-not-break (once code exists)
Tenant scoping on all queries · append-only history tables · honest AI labelling · no mock data in prod builds.

## Stage-2 presentation (2026-10-06)
`pitch/GreenGuardian-Stage2-Review.pptx` — 11 slides following the college template (source was a PDF; rebuilt). Regenerate: `cd pitch && npm install && node build_stage2.js`. Slide content mirrors PRD/MVP_SCOPE; solid = MVP, dashed = planned. **Still blank by design:** student names/IEN/guide (slide 1), team member names (slide 9), signed industry approval letter (slide 11). Gantt uses relative weeks W1–W12 with an assumed Stage 3/4 split at W6.

## Implementation (2026-10-07)
**Backend** (`backend/`): FastAPI + SQLAlchemy 2 + Alembic. Implemented and tested: config (env only), DB layer (pool modes, `search_path`, UUIDv7), problem+json errors, argon2id + JWT auth with rotating refresh tokens and reuse detection, orgs/workspaces/memberships with RBAC, the tenant-isolation route matrix, capability registry, weather behind a provider interface (Open-Meteo adapter verified against the live API; mock for dev/test), migration `0001`, `app.tools.check_db`. 58 tests pass, 2 PostGIS tests are **skipped** (no `TEST_DATABASE_URL`), ruff and mypy clean.
**Frontend** (`frontend/`): see FRONTEND_ARCHITECTURE "Implementation status". 19 tests pass; type-check, lint and production build clean.
**CI** (`.github/workflows/ci.yml`): backend (PostGIS service container; fails if the PostGIS tests are skipped) and frontend jobs. **Not yet run**: the first push will be its first execution.
**Database:** hosted PostgreSQL+PostGIS (Supabase by default) is documented (`docs/DATABASE_SETUP.md`) but **not provisioned**: that needs the team's account and credentials. Until `DATABASE_URL`/`TEST_DATABASE_URL` point at a real PostGIS database, PostgreSQL-specific behaviour (extension install, `search_path`, geometry) is unverified; everything else was tested on SQLite.
**Not built yet:** locations, species/lifecycle, assets, observations, issues, tasks, agent wiring (the rules library exists), map, dashboards with real KPIs, reports, worker/jobs, Dockerfiles.
**Git:** nothing pushed; all work is local commits on `main` pending an explicit instruction to push.
