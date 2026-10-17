# Architecture

## 1. System context

```
 Browser / PWA (React) ──HTTPS──▶ API (FastAPI) ──▶ PostgreSQL + PostGIS
                                     │  ▲                ▲
                                     │  └──── Worker ────┘  (agent runs, rollups, weather sync, reports)
                                     ├──▶ Object storage (S3-compatible: photos, reports)
                                     └──▶ Providers: weather, (later) ML inference, LLM
```

Modular monolith: one backend codebase deployed as two processes — `api` (request/response) and `worker` (scheduled + queued jobs). Frontend is a static SPA.

## 2. Repository layout (target)

```
/docs                    project memory (this folder)
/backend
  /app
    main.py              FastAPI app factory
    core/                config, security, logging, db session, errors, events
    modules/
      identity/          users, orgs, memberships, auth
      workspaces/        workspaces, projects, settings, capability flags
      locations/         fields, zones, geometry
      catalog/           species/crop, lifecycle templates, workflow templates
      assets/            biological assets, plantings, batches, lifecycle events, asset_state projection
      observations/      observations, health/growth records, environment readings, attachments
      issues/            issues, history, evidence, workflow engine
      tasks/             tasks, history, recurrence, inspections, treatments, harvests
      intelligence/      rules engine, recommendations, predictions (reserved), provider interfaces
      dashboards/        dashboard + map query services (read models)
      reports/           report templates & generation
    jobs/                worker entrypoint, schedulers
  /migrations            Alembic
  /tests
/frontend
  /src  app/ routes/ features/ components/ lib/ api/ i18n/
/infra                   docker-compose, Dockerfiles, CI
```

## 3. Backend layering

`router (HTTP, validation, auth deps) → service (business rules, transactions, emits events) → repository (SQLAlchemy queries, workspace scoping)`.

- Routers never touch the ORM directly. Services own transactions (unit-of-work per request).
- **Tenant scoping:** a `WorkspaceContext` dependency resolves the workspace from the path/header + membership + role, and repositories require it — there is no "unscoped" query helper on tenant tables.
- **Domain events** (`observation.created`, `issue.transitioned`, `task.completed`, …) go through an in-process bus; handlers (e.g. enqueue rule evaluation, update `asset_state`) run after commit. Upgrade path: transactional outbox → queue.
- **Errors:** typed domain errors mapped to RFC 7807 problem+json responses; validation errors normalized.
- **Config:** pydantic-settings, env-only; `.env.example` lists names.

## 4. Data architecture

- PostgreSQL 16 + PostGIS. UUIDv7 primary keys (time-ordered), human keys (`GG-001`, `T-014`) per workspace via counters.
- **Append-only time series:** `observation`, `health_record`, `growth_record`, `environment_reading`, `lifecycle_event`, `*_status_history`. State is never overwritten.
- **Current-state projection:** `asset_state` (latest health, growth, stage, last_observed_at, geometry ref, risk flags) maintained by event handlers → fast dashboards/map/rules without scanning history. It is a cache; it can be rebuilt from history (`rebuild_asset_state` job).
- **Spatial:** `geometry(Point, 4326)` for assets, `geometry(MultiPolygon, 4326)` for fields/zones, GiST indexes; area/length computed on `geography` casts.
- Details: [DATABASE_SCHEMA](DATABASE_SCHEMA.md).

## 5. Intelligence architecture
See [AI_ARCHITECTURE](AI_ARCHITECTURE.md). Summary: the Botanical Operations Agent is a worker job that loads rule definitions, evaluates against `asset_state` + recent history, and writes deduplicated `recommendation` rows with explanations. Humans accept/dismiss. Future model providers implement the same interfaces and write `observation`/`prediction`/`recommendation` with provenance.

## 6. Background jobs (MVP)
- DB-backed `job` table (`type, payload, run_at, status, attempts, locked_by`) polled with `SELECT … FOR UPDATE SKIP LOCKED`; APScheduler enqueues periodic jobs (agent sweep per workspace, rollups, weather sync, recurring-task generation).
- Jobs are idempotent and record `job_run` rows (visible in Settings → Agent runs).
- Replace with Celery/RQ + Redis when throughput or fan-out demands it (see DECISION_LOG ADR-005).

## 7. API
REST/JSON, versioned `/api/v1`, OpenAPI generated; TS client generated from the schema. Keyset pagination, filter params, `If-Match`/version on mutable aggregates where concurrent edits matter (issues, tasks). See [API_SPECIFICATION](API_SPECIFICATION.md).

## 8. Frontend
React SPA; feature-sliced; TanStack Query for server state; URL as state for filters; capability-flag-driven future surfaces. See [FRONTEND_ARCHITECTURE](FRONTEND_ARCHITECTURE.md).

## 9. Storage
`Storage` interface (put/get-signed-url/delete) with S3 and local-filesystem implementations. Uploads: authenticated, validated (allow-list MIME, magic bytes, ≤ 10 MB images), keyed `ws/{workspace_id}/obs/{id}/{uuid}.{ext}`, served via short-lived signed URLs. Thumbnails generated in worker.

## 10. Security
See PRD §35. Key invariants: every tenant row has `workspace_id`; every service call takes a `WorkspaceContext`; role checks in services (not only routers); no secrets in code; uploaded files never served from the app origin.

## 11. Observability
Structured JSON logs with request/workspace/user IDs; `/healthz` (liveness) and `/readyz` (DB check); job-run table; error tracking hook (Sentry-compatible); basic metrics endpoint later.

## 12. Deployment
Docker images: `web` (nginx/static or Vercel/Netlify), `api`, `worker`. Managed Postgres+PostGIS; S3-compatible bucket. Migrations (`alembic upgrade head`) as a release step. Config via env. CI (GitHub Actions): lint, type-check, test (Postgres+PostGIS service), build images, OpenAPI client drift check.

## 13. Local development
Database: a hosted PostgreSQL+PostGIS project (Supabase by default) — see `docs/DATABASE_SETUP.md` (ADR-015). Backend: `cd backend && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"`, copy `.env.example` to `.env`, `alembic upgrade head`, `python -m app.tools.check_db`, then `uvicorn app.main:create_app --factory --reload`. Tests: `pytest` (fast, SQLite-backed for non-spatial code; PostGIS tests need `TEST_DATABASE_URL`). Docker/compose is optional and not required.

## 14. Key architectural risks
1. PostGIS availability in dev/CI/prod → mitigated by compose + CI service image.
2. `asset_state` drift → rebuild job + consistency test.
3. Batch-vs-individual asset modelling → single table + `tracking_mode`, tested for both.
4. Rule noise → dedupe keys, per-workspace thresholds, dismissal suppression.
5. Cross-tenant leakage → single scoping path + isolation tests in CI.

## Implementation notes (2026-10-07)

- **Tenant isolation is layered:** (1) `workspace_ctx` is the only way a handler obtains a workspace (404 for non-members); (2) every service query filters by `ctx.workspace_id`; (3) composite foreign keys make cross-tenant links impossible in the database; (4) RLS deny-by-default protects against any other role. An OpenAPI-derived test fails if a `{ws}` route is not in the isolation matrix.
- **Modules** (`app/modules/*`): `identity, workspaces, locations, catalog, assets, observations, issues, tasks, intelligence, weather`, each `models / schemas / service / router` (small modules co-locate schemas in `service.py`). Routers hold no business logic. Dependency direction: `observations → assets, intelligence.runner`; `issues → assets, observations, tasks.mapping`; `tasks → issues, observations`; `intelligence.service → issues, tasks`; no cycles.
- **Transactions:** a service use case ends with one `commit()`; sessions run with `autoflush=False`, so code that must see its own pending changes (projection counts, agent snapshots) flushes explicitly.
- **Test strategy:** the full API suite runs on PostgreSQL in CI. Locally, `GG_TEST_DB=sqlite` (or no `TEST_DATABASE_URL`) is an explicit, reported fast mode for logic iteration; PostgreSQL-only tests (integrity, RLS, PostGIS, smoke) are skipped visibly there. Against a distant hosted database (~130 ms/round trip) only the database-integrity tests, the migration/RLS tests and a compact end-to-end smoke test are run (ADR-026).
- **CI:** see `.github/workflows/ci.yml` (ADR-027).

## Cross-cutting services (2026-10-17)
- **Request context** (`core/request_context.py`, `core/middleware.py`): a pure-ASGI middleware assigns or validates the request ID, resolves the client address (trusting `X-Forwarded-For` only as configured), stores both in `contextvars`, adds `X-Request-ID` to the response, writes one structured access-log line, and converts unhandled exceptions into a generic 500 while the context is still set. Services and loggers read the context without being passed a Request.
- **Throttling** (`modules/identity/throttle.py`): database-backed counters consulted by the identity service before credential checks.
- **Audit** (`modules/audit`): `audit.record_ctx(db, ctx, action, ...)` adds a scrubbed row to the caller's session, so it commits atomically with the change. See `SECURITY.md` and ADR-034.
Flow for a mutating request: `middleware (request id, client ip) -> router (auth, role) -> service (change + audit.record in one transaction) -> commit`.
