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
**Decision:** Keep PostGIS mandatory (spatial is core). Document docker-compose as primary; fallback is a locally installed Postgres+PostGIS or a hosted dev database. No SQLite mode.
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
