# TODO

Legend: `[ ]` open · `[~]` in progress · `[x]` done

## Phase 0 — Foundation
- [x] Repository audit (empty repo)
- [x] Project documentation + PRD
- [ ] Decide dev DB path: install Docker Desktop **or** local Postgres+PostGIS **or** hosted dev DB (needs user input; ADR-007)
- [ ] Monorepo scaffold: `/backend` (FastAPI, uv/pip, ruff, mypy, pytest), `/frontend` (Vite React TS Tailwind shadcn), `/infra` (compose, Dockerfiles)
- [ ] `.gitignore`, `.env.example`, README (setup, run, test)
- [ ] CI (GitHub Actions): lint, types, tests with PostGIS service, frontend build, OpenAPI client drift
- [ ] Alembic baseline + PostGIS extension migration
- [ ] Core: config, logging, error model (problem+json), DB session/UoW, event bus, job runner skeleton

## Phase 1 — Identity & tenancy
- [ ] User/org/workspace/membership models + migrations
- [ ] Register/login/refresh/logout, argon2id, JWT
- [ ] WorkspaceContext dependency + RBAC + **tenant isolation test suite**
- [ ] Workspace create with mode selection; capabilities endpoint
- [ ] Frontend: auth, workspace switcher, app shell with mode-aware nav + future-surface routes

## Phase 2 — Assets
- [ ] Locations (PostGIS), species/lifecycle seed data (both modes), assets + lifecycle events
- [ ] Asset list (table/map split), asset profile, create/edit, archive

## Phase 3 — Monitoring
- [ ] Observations + attachments (storage abstraction, validation), health/growth records, `asset_state` projection + rebuild job
- [ ] Charts, timeline, observation form (mobile-first)

## Phase 4 — Operations
- [ ] Workflow engine + Issues (history, evidence, resolution)
- [ ] Tasks (history, recurrence), treatments, harvest records

## Phase 5 — Agent
- [ ] Rule interface + MVP rules with table-driven tests, dedupe/suppression, recommendations API, inbox UI, run history, rule settings

## Phase 6 — Map & dashboards
- [ ] `/map` GeoJSON + layer registry, MapLibre UI, draw tools
- [ ] `/dashboard` (green + agri), KPI availability semantics

## Phase 7 — Reports, weather, surfaces, polish
- [ ] Reports (analytics, impact, CSV), weather provider
- [ ] Future-surface pages (Crop Rec, Disease, Growth, Survival, Yield, Harvest, Irrigation, Financials) via CapabilityGate
- [ ] Accessibility + responsive pass, i18n extraction

## Phase 8 — Hardening
- [ ] 100k-asset perf seed, Playwright golden path (both modes), security review, deployment docs

## Open questions for the user
1. Dev DB path (Docker vs local PostGIS vs hosted)?
2. Weather provider preference (e.g. Open-Meteo, free/no key)? *Default assumption: Open-Meteo.*
3. Deployment targets (Vercel/Railway/Render/VM)? *Default: containers + static hosting.*
