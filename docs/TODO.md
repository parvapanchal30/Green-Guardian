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
- [x] Stage C (2026-10-18): scheduled agent worker, run history, `irrigation_defer`, rule versions, recommendation lifecycle (ADR-039..042)
- [ ] Stage C follow-ups: workspace settings UI for the agent schedule and thresholds; retention for `agent_runs`; wire `symptom_cluster` (needs multi-asset issues); validate irrigation thresholds once irrigation logs or soil sensors exist
- [ ] Stage D: data and ML foundations (dataset catalog and licences, labelling workflow, versioned splits, evaluation harness): investigate datasets and licensing before any model
- [x] Full API suite ran on PostgreSQL in CI (run 3)
- [x] `GET /dashboard` and map read models
- [x] Photo upload with storage abstraction and validation (2026-10-17); [ ] signed URLs / S3 adapter, thumbnails, purge job
- [x] Lifecycle events, templates, exits, corrections, survival and harvest KPIs (ADR-055); [ ] species lifecycle durations (need domain input), partial batch loss, harvest quantities and yield records, workspace-specific templates
- [x] Worker + scheduler: periodic agent runs; weather-aware irrigation-deferral rule using the existing port (Stage C)
- [ ] Recurring inspection tasks (the agent suggests inspections; recurring task templates are not built)
- [ ] Member invite/role UI; workspace settings UI for agent thresholds
- [ ] Reports (analytics/impact, CSV) from records; survival rate once loss/planting records exist
- [ ] Decide on a local PostgreSQL+PostGIS (or Docker) for developers so the whole suite can run locally on PostgreSQL
- [ ] Revisit the advisor's unindexed-foreign-key notices with real query statistics before production
- [ ] Open-Meteo commercial licence decision (R-WX-1) before any commercial deployment

- [x] Stage D foundations (2026-10-18, synthetic fixtures only): dataset catalog and licence verification, label review, quality checks, grouped splits, evaluation harness, reviewer agreement, claim gate (ADR-044)
- [ ] Datasets page (catalog + blocker checklist, evidence entry, review queue, quality and claim panels)
- [ ] Owner: read the official licence pages of the candidates in `docs/datasets/candidates.json` and record the evidence; decide how PlantDoc's scraped images are treated (written confirmation from the authors, or keep it excluded)
- [ ] Evaluation-protocol registry (needs the owner's acceptance criteria and field-domain test data); a qualified, verifiable plant-health reviewer
- [ ] Label import/export (CSV) with provenance; retention policy for dataset records

- [x] Stage D1 (2026-10-18): licence evidence verified at official sources for six candidates; worksheet importer (ADR-045)
- [x] Stage D2: Datasets UI (catalog, evidence, blockers, approval workflow, review queue, quality, splits, agreement, claim gate) (ADR-046)
- [x] Stage D3: evaluation-protocol proposal P-DIS-1 and registry with sign-offs (ADR-047)
- [ ] Owner: decide the open image-origin questions (Cassava, Irish potato, PlantNet), reject PlantVillage in the catalog, and confirm the pending protocol thresholds with a qualified plant pathologist
- [ ] A qualification-verification mechanism (needed before any protocol can be approved)
- [x] Cluster bootstrap and risk-coverage metrics; claim gate aligned with the 139-per-class rule (ADR-049)
- [x] Sample registration and CSV import in the UI (ADR-050)
- [ ] Owner: connect GitHub to the Vercel project (or sign in the Vercel CLI), set the production branch, then create the first preview deployment (HOSTING.md section 9)
- [ ] Owner: choose and approve an API/worker host, domains and a staging database; then deploy and verify (HOSTING.md section 10)
- [x] S3-compatible evidence storage adapter (ADR-052); [ ] verify it against a real bucket with `python -m app.tools.storage_check` once a provider is approved
- [ ] Error-reporting service and alerting; first real backup and restore rehearsal
- [ ] Owner: read the `git_info_fail` build log or confirm Settings > Git on `greenguardian-web`; choose a release branch and set it as the Vercel Production Branch (ADR-051)
- [ ] Owner: when a staging API exists, replace the Preview `VITE_API_BASE_URL` placeholder (it now fails builds on purpose)
- [ ] Owner decisions for staging (STAGING.md section 8): API/worker host and plan, storage provider, staging Supabase project, region, aliases, alert recipients
- [ ] Purge job for soft-deleted evidence blobs; database-backed worker heartbeat for hosts without exec health checks; error-reporting integration; advisory lock or single-step guard around `alembic upgrade`

- [ ] Owner decision: is the project commercial? (Vercel Hobby is non-commercial only; Supabase Free terms to be checked) (ZERO_COST.md)
- [ ] Zero-cost API on Vercel Functions: module-level `app` shim, transaction-pooler settings, `STORAGE_MAX_BYTES` about 4 MB with browser-side resize, region near Seoul, then measure cold start (needs owner approval to create the Vercel API project; not done)
- [ ] Tick endpoint for a daily Vercel Cron (secret-protected, due-tolerance of about 2 h) as the zero-cost worker compromise; design in ZERO_COST.md section 2.3
- [x] Evidence reconciler and `Attachment.storage_key` removal (ADR-054); [ ] retention policy and purge for soft-deleted evidence blobs; [ ] run the reconciler once against a real bucket after a provider is approved (deferred with hosting)
- [ ] Verify unverified free-tier facts before relying on them (ZERO_COST.md section 6): Supabase S3 on Free, region ids, pause behaviour, Supabase Cron
- [x] Migrations 0011 and 0012 on the development database (found applied on 2026-10-23; `alembic check` clean) and the full backend suite on PostgreSQL (994 passed; the 6 test faults fixed and re-verified)
- [x] Harvest records, corrections, per-unit totals, Yield KPI, asset-page panel (ADR-056); [ ] seasons / crop cycles, yield per area (needs areas), prices and revenue, harvest forecasting (needs data and a protocol)
- [ ] Tours: more in-app steps (tasks and issues detail, observation form), a first-run prompt for new workspaces, translations; keep `frontend/tour/steps.json` and `frontend/src/tour/steps.ts` aligned
- [x] i18n foundation (English, Hindi) and the main screens (ADR-058); [x] migrate the remaining screens (2026-10-22); [ ] Hindi narration for the automated browser tour (`steps.json`, optional); [ ] API codes for server-composed text; [ ] **native-speaker review of the Hindi catalog**; [ ] language preference stored on the account
- [x] Actions as records and the verification rule (ADR-059, 2026-10-23); [x] migration 0013 on the development database (2026-10-25); [x] recurring inspection schedules (ADR-062, 2026-10-25); [x] migration 0014 on the development database (2026-10-25); [ ] calendar rules (weekdays, months, seasons), per-plant tasks for a location, routines for watering and other work; [ ] location-level work, costs and stock; [ ] verification figures on the dashboard
- [x] Every API timestamp is timezone-aware, also from SQLite (`UtcDateTime`, ADR-060)
- [x] Fixed, documented passwords for the local demo accounts (ADR-061)
- [ ] Next product milestone candidates: recurring inspection schedules, partial batch loss (a count ledger), workspace settings UI for agent thresholds, member invite/role UI
