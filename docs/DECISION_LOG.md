# Decision Log

Format: ID · date · status · context → decision → consequences. Newest at bottom. Never delete; supersede.

## ADR-001 · 2026-10-06 · Accepted — Adopt the recommended stack (greenfield)
**Context:** The GitHub repository `parvapanchal30/Green-Guardian` was empty (no commits) at audit time, so there was no existing stack to retain.
**Decision:** React+TS+Vite+Tailwind+shadcn/ui (frontend); FastAPI+Pydantic v2+SQLAlchemy 2+Alembic (backend); PostgreSQL 16+PostGIS.
**Consequences:** Python is the natural home for later ML/CV; TS end-to-end types via OpenAPI codegen; PostGIS is a hard dependency (see ADR-007).

## ADR-002 · 2026-10-06 · Accepted — Modular monolith, not microservices
**Decision:** One backend codebase, `api` + `worker` processes, domain modules with strict layering. Extract ML inference as a service only when it needs independent scaling/hardware.
**Why:** Small team, tight domain coupling, transactional integrity across issue/task/history.

## ADR-003 · 2026-10-06 · Accepted — One BiologicalAsset table with `kind` + `tracking_mode`
**Decision:** Trees, plants, crop batches share `biological_asset`; population assets (batches) carry `estimated_count`, optional child individuals via `parent_asset_id`.
**Why:** Avoid redundant per-screen entities; agriculture and green management share the graph. **Tradeoff:** sparse columns/`attributes jsonb`; mitigated by per-kind validation in services.

## ADR-004 · 2026-10-06 · Accepted — Append-only time series + `asset_state` projection
**Decision:** Observations, health/growth records, lifecycle events and status histories are immutable; current state is a rebuildable projection.
**Why:** Time-aware state, auditability, future ML training data, fast dashboards. **Tradeoff:** projection maintenance; mitigated by rebuild job and consistency test.

## ADR-005 · 2026-10-06 · Accepted — DB-backed jobs + APScheduler for MVP (no Celery/Redis yet)
**Decision:** `job` table with `SKIP LOCKED` + scheduler in the worker process.
**Why:** Fewer moving parts; load is low; Postgres already required. **Revisit when:** fan-out/throughput or retry semantics outgrow it → Celery/RQ + Redis (V2).

## ADR-006 · 2026-10-06 · Accepted — Mode is configuration, not a fork
**Decision:** `workspace.mode` selects vocabulary, dashboard composition, default lifecycle template and nav emphasis. Same schema/API.
**Why:** Central product thesis; avoids two apps.

## ADR-007 · 2026-10-06 · Accepted — PostGIS required; Docker is the documented dev path
**Context:** The current dev machine has no Docker installed.
**Decision:** Keep PostGIS mandatory (spatial is core). *Amended by ADR-015:* development uses a hosted PostgreSQL+PostGIS database; docker-compose remains optional. SQLite is allowed **in fast unit tests only**, never as a runtime target.
**Consequences:** Dev environment setup is the first scaffold task (see TODO).

## ADR-008 · 2026-10-06 · Accepted — Capability-flagged future surfaces, never fabricated outputs
**Decision:** Future intelligence UIs ship as real layouts behind `CapabilityGate`; API returns `available:false`/`501 capability_unavailable`. Dev sample data only behind an explicit flag and watermarked, excluded from prod builds.
**Why:** Avoid redesign when features land without misleading users.

## ADR-009 · 2026-10-06 · Accepted — Rules-first Botanical Operations Agent with human acceptance
**Decision:** MVP agent = deterministic rules writing `recommendation`s with explanations; acceptance by a human creates Issue/Task through normal services. Interfaces for Detector/Predictor/Recommender defined now.
**Why:** Honest, explainable, immediately useful; collects data for later models.

## ADR-010 · 2026-10-06 · Accepted — First-party JWT auth behind an interface
**Decision:** argon2id passwords, short-lived access + rotating refresh tokens, workspace RBAC; interface allows OIDC later.
**Why:** No external dependency for MVP; SSO is V2.

## ADR-011 · 2026-10-06 · Accepted — Workflow and lifecycle as data templates
**Decision:** Issue/task workflows and asset lifecycles are template rows validated by a generic engine.
**Why:** Different issue categories and modes need different flows without code forks.

## ADR-012 · 2026-10-06 · Accepted — Roadmap stages: MVP → V2 Prediction → V3 Recommendation → V4 Optimization
**Context:** The earlier roadmap grouped yield/harvest prediction and crop recommendation into one V3. The product brief and Stage-2 deck define the evolution as Prediction → Recommendation → Optimization.
**Decision:** V2 = disease detection, growth/survival/yield/harvest prediction; V3 = crop and irrigation recommendation, profitability, LLM layer; V4 = optimization. Yield/harvest prediction stays gated on sufficient real history.
**Consequences:** PRD §38 and FUTURE_ROADMAP updated; deck and docs use identical stage names.

## ADR-013 · 2026-10-06 · Accepted — Stage-2 deck is built from code and mirrors the college template
**Decision:** `pitch/build_stage2.js` (pptxgenjs) regenerates `pitch/GreenGuardian-Stage2-Review.pptx`: 11 slides, template fonts/positions, monochrome. Solid = MVP, dashed = planned. Content must match these docs; no unimplemented capability may appear as solid.
**Why:** The original template was supplied as PDF only; scripted rebuild keeps edits reviewable. Slide titles on pages 6–11 were moved to the top (template placed them mid-page) to make room for diagrams.

## ADR-014 · 2026-10-06 · Accepted — Rules engine proof of concept is pure Python
**Decision:** `backend/app/modules/intelligence/rules/` holds dataclass-based rules (inspection gap, health decline, symptom cluster) with no DB/I/O; tests in `backend/tests/`. `backend/poc_run.py` runs it on clearly labelled synthetic data.
**Why:** Demonstrates the agent design honestly before infrastructure exists; same interfaces will be called by the worker service.

## ADR-015 · 2026-10-07 · Accepted — Hosted PostgreSQL + PostGIS (Supabase by default) for development, portable by construction
**Context:** No Docker/PostgreSQL on the dev machine. Team decision: use a hosted database, Supabase unless something requires otherwise.
**Decision:** Treat Supabase as "managed PostgreSQL+PostGIS" only. All access via the backend (SQLAlchemy 2 + Alembic + psycopg 3). No Supabase client SDK, Auth, Storage, RLS or Data API; no provider-specific SQL in migrations. PostGIS lives in a dedicated schema (`POSTGIS_SCHEMA`, default `extensions`) and each connection sets `search_path` itself. Pool mode (`session` default / `transaction` → NullPool + no prepared statements) and the IPv4/IPv6 connection choice are env-driven. Requirements and one-time setup: `docs/DATABASE_SETUP.md`. Credentials only in env/`.env`; `.env.example` has names.
**Consequences:** Switching provider = env change (+ `POSTGIS_SCHEMA` if PostGIS must live in `public`). Creating the Supabase project is a human step (account + credentials). Until `TEST_DATABASE_URL` is set, PostgreSQL/PostGIS-specific behaviour is **not verified** by tests (2 gated tests skip with an explicit reason); CI must provide a PostGIS service.

## ADR-016 · 2026-10-07 · Accepted — Synchronous SQLAlchemy + psycopg 3; services commit explicitly
**Decision:** Sync engine/sessions (FastAPI runs sync handlers in a threadpool); psycopg 3 driver; each service use case ends with an explicit `commit()`; the `get_db` dependency only opens/closes the session. UUIDv7 ids generated in Python.
**Why:** Simplest correct model for CRUD + Alembic; avoids dependency-exit-timing ambiguity; async can be introduced per hot path later.

## ADR-017 · 2026-10-07 · Accepted — Tenancy contract: 404 for non-members, role checks in dependencies and services, route-matrix test
**Decision:** `workspace_ctx` is the only way a handler obtains a workspace; non-members and unknown ids both get `404 workspace_not_found`; insufficient role gets `403`. Only owners can grant/change/remove the owner role; a workspace always keeps ≥1 owner. `tests/test_tenancy.py` derives all `{ws}` routes from the OpenAPI schema and fails if any route is missing from the isolation matrix.
**Why:** Makes "every endpoint has an isolation test" mechanically enforced instead of a convention.

## ADR-018 · 2026-10-07 · Accepted — Weather behind a provider interface; Open-Meteo first
**Decision:** `WeatherProvider` protocol + provider-neutral `Forecast/HourlyPoint`; `OpenMeteoProvider` adapter; `MockWeatherProvider` (dev/test only, refused when `ENV=production`, output labelled `source=mock`); `WeatherService` adds a coordinate-rounded TTL cache; provider failures map to `503 weather_unavailable` without leaking internals. Pure helper `expected_precipitation_mm` is ready for the future irrigation-deferral rule.
**Risk R-WX-1:** Open-Meteo's free API is for **non-commercial use**; a commercial deployment needs an API key/customer endpoint or a different provider. Swap = new adapter + `WEATHER_PROVIDER` value.

## ADR-019 · 2026-10-07 · Accepted — Capability registry lives in code; workspace overrides can only disable
**Decision:** `modules/workspaces/capabilities.py` is the source of truth for which intelligence features are live; `GET /workspaces/{ws}/capabilities` exposes it. Overrides stored on the workspace may switch a live capability off but can never enable an unbuilt one (tested).
**Why:** Enforces ADR-008 (no fabricated features) server-side, not just in the UI.

## ADR-020 · 2026-10-07 · Accepted — Frontend foundations
**Decisions:** React 19 + TS + Vite + Tailwind v4 (tokens in `index.css`, light/dark via `prefers-color-scheme`), React Router, TanStack Query with workspace-scoped keys; hand-written API types for now (OpenAPI codegen once the surface grows); dev uses a Vite same-origin proxy to the API (no CORS locally). shadcn/ui is **not** installed yet: components are small and local until a pattern repeats enough to justify it.
**Navigation registry** (`src/app/routes.ts`) drives the sidebar, mode-awareness and status labels: `live` (implemented), `building` (MVP, "In development"), `soon` (V2+, "Coming soon", must name a backend capability and technique). Tests assert only implemented routes are `live` and every `soon` route is capability-gated.
**Auth storage:** access token in memory, refresh token in `sessionStorage` (per tab), single-flight refresh. Known limitation: a *duplicated tab* copies the refresh token, and the server's reuse detection then revokes all sessions. Planned fix: httpOnly cookie and/or a short reuse grace window (see TODO).
**Status semantics:** never colour-only; each tone has a glyph and text.

## ADR-021 · 2026-10-07 · Accepted — PostGIS tests run in a throwaway schema; connections fail fast with a diagnosis
**Context:** First real-database run failed twice for environmental reasons (password with Supabase's `[ ]` placeholder brackets; no IPv6 route to the IPv6-only direct host). The PostGIS tests also used `alembic downgrade base`, which would drop real tables if `TEST_DATABASE_URL` pointed at the dev database.
**Decision:** (1) `Settings.db_schema` (default `public`) is the first `search_path` entry; Alembic honours it for the version table; the PostGIS tests create `gg_test_<random>`, migrate inside it and `DROP SCHEMA ... CASCADE` afterwards. (2) `DB_CONNECT_TIMEOUT_S` bounds connects; `check_db` probes TCP per address family and names the cause (IPv6-only host unreachable, DNS, wrong password). (3) A bracket-wrapped password is rejected at settings load.
**Consequence:** the test suite is safe to point at any database that has PostGIS; common setup mistakes produce an actionable message instead of a hang.

## ADR-022 · 2026-10-07 · Accepted — Application tables live in a dedicated schema, never `public`
**Context:** Supabase exposes `public` through the Data API with default grants to `anon`/`authenticated`; our tables have no RLS (the backend enforces tenancy). Verified with the connector that the dedicated schema has no such grants.
**Decision:** `DB_SCHEMA` (default `greenguardian`) is the first entry of `search_path`; the migration environment creates it and keeps `alembic_version` in it; `check_db` fails if application tables appear in `public`. PostGIS stays in `extensions`. `DB_SSLMODE` (default `require`) is applied unless the URL carries its own `sslmode`.
**Also:** `TEST_DATABASE_URL` may equal `DATABASE_URL` because database tests are confined to a generated throwaway schema with a before/after canary (see DATABASE_SETUP section 5). RLS is documented as optional defence-in-depth, not applied (provider-specific; the backend role bypasses RLS).

## ADR-023 · 2026-10-07 · Accepted — RLS deny-by-default, owner/BYPASSRLS runtime role, API roles locked out
Enable RLS on every application table with no policies; revoke all schema/table/sequence/function privileges (and default privileges) from `anon`/`authenticated` where those roles exist; do not use `FORCE`. Verified facts: the backend role `postgres` owns the tables and has `BYPASSRLS`; `anon`/`authenticated` have neither. `app.core.rls` provides the helpers; a guard test and `check_db` enforce coverage. Introducing a separate non-owner runtime role later requires explicit policies in the same migration. **Consequence:** the advisor's critical "RLS disabled" finding is replaced by the intended INFO "RLS enabled, no policies".

## ADR-024 · 2026-10-07 · Accepted — Weather behind an agent-owned port; registry-selected providers
`WeatherContextProvider` (in `intelligence/ports.py`) is what the agent depends on; `ForecastWeatherContext` adapts any `WeatherService`/`WeatherProvider`; `weather/registry.py` maps `WEATHER_PROVIDER` to a factory (unknown keys fail at startup). AST-based tests enforce: the agent package never imports `weather`; only the registry imports concrete providers; Open-Meteo is mentioned in code only in config, its adapter and the registry. Open-Meteo stays the default; the commercial-use licensing risk (R-WX-1, facts and date in DATABASE_SETUP section 7) must be resolved before commercial deployment. The paid-API mechanics were not verifiable from the terms page, so none is implemented.

## ADR-025 · 2026-10-07 · Accepted — First vertical slice: domain decisions
One `biological_assets` table for trees/plants/batches; `asset_states` projection updated synchronously and rebuildable; observations carry health (no HealthRecord yet) and are append-only; issues are first-class with workflow-as-code, status history and resolution columns; tasks have their own workflow and may carry a follow-up observation on completion; recommendations are only created by rules and decided by a person; composite tenant FKs; deferred entities listed in DATABASE_SCHEMA. Agent quality rules discovered through tests: `health_decline` baseline resets after a resolved issue; at most one issue proposal per asset; just-registered assets are not "overdue"; a task with an open inspection suppresses the inspection rule. Closing an issue with open tasks is blocked unless the caller explicitly cancels them.

## ADR-026 · 2026-10-07 · Accepted — Test infrastructure: PostgreSQL session schema, savepoint rollback, explicit fast mode
`world` fixture: PostgreSQL mode migrates one throwaway schema per session (canary-checked before/after), seeds a team by direct inserts (tokens minted locally), and wraps each test in an outer transaction with `join_transaction_mode="create_savepoint"` so service `commit()` calls are savepoint releases. SQLite remains only as a reported fast mode. **Finding:** against a remote hosted database (~130 ms/round trip, ~15 statements per request) the full API suite is impractical (one 45-request test took 538 s and hit a ~9-minute connection lifetime limit on the pooler). Local verification on hosted PostgreSQL therefore uses the integrity/RLS/migration tests plus a compact end-to-end smoke test; the complete suite runs on PostgreSQL in CI.

## ADR-027 · 2026-10-07 · Accepted — CI design
Backend job: `postgis/postgis` service with trust auth (no stored password); a database created from `template0` so the migration installs PostGIS into `extensions` like hosted providers (the image preinstalls it into `public`); `DB_SSLMODE=disable` only inside the workflow; `GG_REQUIRE_POSTGRES_TESTS=1`; steps: ruff, format check, mypy, migrate, `alembic check`, `check_db`, downgrade/upgrade cycle, pytest. Fixed defects found by review: a `pytest | tee; ! grep` pipeline that would have hidden test failures, a colon in a step name that made the YAML invalid, a hard-coded password. Validated with `actionlint` and by reproducing the steps locally against Supabase in a fresh venv and clean copy (without `.env`). Not yet executed on GitHub.

## ADR-028 · 2026-10-07 · Accepted — SQLite engine details for tests/smoke runs
`StaticPool` only for in-memory SQLite; file databases use a normal pool (a shared single connection corrupted concurrent requests in a browser smoke run and produced spurious 404/500 responses). SQLite remains tests/smoke only and returns timezone-naive datetimes (clients mis-read them); PostgreSQL returns timezone-aware values.
