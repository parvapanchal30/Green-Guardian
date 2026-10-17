# TODO

Legend: `[ ]` open · `[~]` in progress · `[x]` done

## Phase 0 — Foundation
- [x] Repository audit (empty repo)
- [x] Project documentation + PRD
- [x] Stage-2 review deck (pitch/) — fill names, IEN, guide, approval letter
- [x] Rules-engine proof of concept (pure Python, 5 tests)
- [x] Dev DB path decided: hosted PostgreSQL+PostGIS, Supabase by default (ADR-015)
- [x] **Human step done 2026-10-07:** create the Supabase project, enable PostGIS in schema `extensions`, set `DATABASE_URL` + `TEST_DATABASE_URL` (docs/DATABASE_SETUP.md), run `alembic upgrade head` and `python -m app.tools.check_db`, then `pytest` so the PostGIS tests actually run
- [x] Monorepo scaffold (backend + frontend done; `/infra` Dockerfiles still to do): `/backend` (FastAPI, uv/pip, ruff, mypy, pytest), `/frontend` (Vite React TS Tailwind shadcn), `/infra` (compose, Dockerfiles)
- [x] `.gitignore`, `.env.example`, READMEs
- [x] CI green on GitHub (run 3, 2026-10-17); OpenAPI client drift check still to add
- [x] Alembic baseline + PostGIS extension migration (PostGIS step unverified without a real DB)
- [x] Core: config, logging, error model, DB session
- [ ] Core: event bus, job runner skeleton

## Phase 1 — Identity & tenancy
- [x] User/org/workspace/membership models + migrations
- [x] Register/login/refresh/logout, argon2id, JWT
- [x] Login rate limiting (2026-10-17); [ ] refresh-token reuse grace window or httpOnly cookie (duplicated-tab limitation), email verification, password reset
- [x] WorkspaceContext dependency + RBAC + **tenant isolation test suite**
- [x] Workspace create with mode selection; capabilities endpoint
- [x] Frontend: auth, workspace switcher, app shell with mode-aware nav + future-surface routes
- [ ] Frontend: member invite/role UI, screenshot-based visual review

## Phase 2 — Assets
- [x] Locations (PostGIS), species seed data, assets; [ ] lifecycle events and templates
- [x] Asset list, asset profile, create/edit, archive; map is a separate page

## Phase 3 — Monitoring
- [x] Observations, `asset_state` projection, evidence upload (storage abstraction, validation); [ ] health/growth record series, projection rebuild job, thumbnails
- [ ] Charts, timeline, observation form (mobile-first)

## Phase 4 — Operations
- [x] Workflow engine + Issues (history, evidence, resolution)
- [x] Tasks (history); [ ] recurrence, treatments, harvest records

## Phase 5 — Agent
- [x] Rule interface, 3 rules, tests, dedupe/suppression, recommendations API, inbox UI; [ ] run history, rule settings UI, scheduler

## Phase 6 — Map & dashboards
- [x] `/map` GeoJSON + layer registry, Leaflet UI; [ ] draw tools
- [x] `/dashboard` (green + agri), KPI availability semantics

## Phase 7 — Reports, weather, surfaces, polish
- [ ] Reports (analytics, impact, CSV), weather provider
- [ ] Future-surface pages (Crop Rec, Disease, Growth, Survival, Yield, Harvest, Irrigation, Financials) via CapabilityGate
- [ ] Accessibility + responsive pass, i18n extraction

## Phase 8 — Hardening
- [ ] 100k-asset perf seed, Playwright golden path (both modes), security review, deployment docs

## Open questions for the user
1. ~~Dev DB path~~ decided: hosted PostGIS (Supabase).
2. ~~Weather provider~~ decided: Open-Meteo behind an interface. **Risk R-WX-1:** the free tier is non-commercial only; decide before any commercial deployment.
3. ~~Deployment~~ decided: static frontend hosting/CDN, containerized FastAPI, managed PostgreSQL+PostGIS, containerized workers when needed. Dockerfiles still to write.

## Database follow-ups
- [x] RLS enabled on every table (migrations 0002, 0004)
- [ ] Optional: a separate Supabase project/branch for tests if the team wants hard separation
- [x] `TEST_DATABASE_URL` (tests use a throwaway schema, never dev data)

## Next slice candidates (recommended order)
- [x] Stage A2: login throttling, request IDs, audit trail (2026-10-17)
- [x] Stage A3 (2026-10-18): Dockerfiles and compose stack, deployment doc, backup/restore procedure with CI proof, audit log UI and retention, 403 access-denied events
- [ ] Take and rehearse the first real backup of the Supabase database (needs PostgreSQL 17 client tools on a machine you control)
- [ ] S3-compatible storage adapter (needed before running more than one API replica)
- [ ] Choose a hosting provider and a map tile provider; decide the Open-Meteo commercial question (R-WX-1)
- [ ] Stage C: scheduled agent worker, `irrigation_defer` rule, rule configuration and versioning
- [x] Full API suite ran on PostgreSQL in CI (run 3)
- [x] `GET /dashboard` and map read models
- [x] Photo upload with storage abstraction and validation (2026-10-17); [ ] signed URLs / S3 adapter, thumbnails, purge job
- [ ] Lifecycle events and templates (read-only `current_stage` today); species lifecycle durations
- [ ] Worker + scheduler: periodic agent runs, recurring inspection tasks; weather-aware irrigation-deferral rule using the existing port
- [ ] Member invite/role UI; workspace settings UI for agent thresholds
- [ ] Reports (analytics/impact, CSV) from records; survival rate once loss/planting records exist
- [ ] Decide on a local PostgreSQL+PostGIS (or Docker) for developers so the whole suite can run locally on PostgreSQL
- [ ] Revisit the advisor's unindexed-foreign-key notices with real query statistics before production
- [ ] Open-Meteo commercial licence decision (R-WX-1) before any commercial deployment
