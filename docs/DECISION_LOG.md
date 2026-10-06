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
