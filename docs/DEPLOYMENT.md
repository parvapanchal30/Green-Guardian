# Deployment

> **Hosting plan (frontend on Vercel, API and worker on a container host): see [HOSTING.md](HOSTING.md).** This document describes packaging, the compose stack, releases and operations; HOSTING.md has the Vercel setup, the environment matrix, what is verified and the manual steps still needed.

How GreenGuardian is packaged and how a deployment should be built. **Nothing is deployed yet and no paid or public resource has been created**; this document is the plan plus the parts that are already built and verified. Verification status is stated at the end (section 12).

## 1. Components and topology

```
 Browser ──HTTPS──►  Edge (TLS, HSTS, optional CDN)
                       │
                       ▼
                 web  (nginx, static SPA, /api proxy)  ── security headers, request ID, SPA fallback
                       │  /api/*  (X-Request-ID, X-Forwarded-For)
                       ▼
                 api  (FastAPI, uvicorn, 1 process per container) ──► object store (evidence photos)
                       │                                   ▲
                       ▼                                   │ same image, different command
              PostgreSQL + PostGIS  ◄────────────────  worker (Stage C: scheduled agent, housekeeping)
```

| Component | Packaging | State | Scales by |
|---|---|---|---|
| web | `frontend/Dockerfile` (node build, then unprivileged nginx, uid 101, port 8080) | none | more containers, or host `dist/` on any static host/CDN |
| api | `backend/Dockerfile` (python 3.12-slim, venv copied from a build stage, uid 10001, port 8000) | none (stateless) | more containers |
| migrate | the api image, command `alembic upgrade head` | none | run once per release, never per replica |
| worker | the api image, `python -m app.worker` (scheduled agent runs and housekeeping) | none (state is in the database) | one is enough; more are safe but redundant (a database index prevents overlapping runs) |
| database | managed PostgreSQL 15+ with PostGIS (dev: Supabase; local compose: `postgis/postgis:17-3.5`) | all data | provider plan |
| object store | local volume today (`STORAGE_PROVIDER=local`) | evidence files | see 9 |

Provider-specific code stays behind interfaces: the weather provider (`WEATHER_PROVIDER`), the object store (`STORAGE_PROVIDER`), and the database URL. Nothing in the application names a hosting vendor.

## 2. Candidate hosting (a choice for you, not yet made)
The stack is deliberately portable. Reasonable shapes, none provisioned:
- **Single small VM** running the compose file with a managed or local PostGIS: cheapest, simplest, one failure domain.
- **Container platform** (Railway, Render, Fly.io, Cloud Run, ECS): api, web and worker as separate services; managed PostgreSQL with PostGIS; an S3-compatible bucket once that adapter exists.
- **Static host/CDN for the frontend** (Vercel, Netlify, Cloudflare Pages) plus a container host for the API: then set `VITE_API_BASE_URL` to the API origin at build time and add that origin to `CORS_ORIGINS`.
Cost, region and data-residency decisions are yours; I will not create billable resources without your approval.

## 3. Environments
| | development | test (CI) | staging | production |
|---|---|---|---|---|
| purpose | day-to-day work | automated gates | rehearsal with production-like settings | real users |
| `ENV` | `development` | `test` | `production` | `production` |
| database | Supabase dev project or local compose | throwaway PostGIS container | separate database, same engine and extensions as production | managed PostGIS with backups (BACKUP_RECOVERY.md) |
| `DB_SSLMODE` | `require` (hosted) / `disable` (compose) | `disable` | `require` or `verify-full` | `verify-full` where the provider supports it |
| secrets | `backend/.env` (gitignored) | none (trust auth, throwaway) | platform secret store | platform secret store |
| `JWT_SECRET` | generated, 32+ chars, unique per environment | fixed test value | unique | unique, rotated on suspicion of leak |
| `STORAGE_PROVIDER` | `local` | `memory` (tests) | `local` on a volume or object store | durable volume or object store |
| `WEATHER_PROVIDER` | `open_meteo` | `mock` | `open_meteo` | `open_meteo` only after the licensing decision (R-WX-1) |
| `TRUSTED_PROXY_COUNT` | 0 | 0 | number of proxies in front | number of proxies in front |
| `CORS_ORIGINS` | `http://localhost:5173` | n/a | the staging web origin(s) | the production web origin(s) only |
`ENV=production` additionally refuses to start with a short `JWT_SECRET`, the mock weather provider, the in-memory store, any `CORS_ORIGINS` entry that is not an exact https origin (no wildcard, no localhost, no path or trailing slash), or a database connection without TLS. Every environment except `test` refuses to start without a 32+ character `JWT_SECRET`.

## 4. Environment variables (backend)
Secrets are marked **S**. Names only appear in Git (`backend/.env.example`, `.env.compose.example`); values live in the platform's secret store or a gitignored file.

| Variable | Default | Meaning |
|---|---|---|
| `ENV` | `development` | `development`, `test` or `production` |
| `LOG_LEVEL` | `INFO` | structured JSON logs; every line carries the request ID |
| `DATABASE_URL` **S** | required | PostgreSQL URL (`postgresql://user:password@host:5432/db`); URL-encode special characters |
| `DB_SCHEMA` | `greenguardian` | application schema (not `public`) |
| `POSTGIS_SCHEMA` | `extensions` | where PostGIS lives |
| `DB_SSLMODE` | `require` | `disable` only for a TLS-less local container |
| `DB_POOL_MODE`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_CONNECT_TIMEOUT_S`, `DB_POOL_PRE_PING` | `session`, 5, 5, 10, true | connection pool (see DATABASE_SETUP.md section 10) |
| `JWT_SECRET` **S** | required | 32+ characters |
| `JWT_ALGORITHM`, `ACCESS_TOKEN_TTL_MINUTES`, `REFRESH_TOKEN_TTL_DAYS` | HS256, 15, 30 | token policy |
| `AUTH_*` | see SECURITY.md | login, refresh and registration throttling |
| `AUDIT_RETENTION_DAYS` | 730 | 0 = keep forever; otherwise at least 30 |
| `AUDIT_DENIED_DEDUPE_S` | 60 | de-duplication window for access-denied events |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | JSON list of allowed browser origins (not needed behind the same-origin nginx proxy) |
| `TRUSTED_PROXY_COUNT` | 0 | reverse proxies in front (controls the client address used for throttling and audit) |
| `WEATHER_PROVIDER`, `OPEN_METEO_BASE_URL`, `WEATHER_TIMEOUT_S`, `WEATHER_CACHE_TTL_S` | `open_meteo`, ..., 8, 900 | weather context |
| `WORKER_POLL_INTERVAL_S` | 60 | how often the worker looks for workspaces whose agent run is due |
| `AGENT_STALE_RUN_S` | 1800 | a run still `running` after this long is presumed abandoned and failed |
| `HOUSEKEEPING_INTERVAL_S` | 86400 | audit retention and idle throttle counters, run by the worker |
| `STORAGE_PROVIDER`, `STORAGE_LOCAL_DIR`, `STORAGE_MAX_BYTES`, `STORAGE_MAX_PIXELS` | `local`, `var/storage`, 10 MB, 40 MP | evidence storage |

Frontend (build time, public values only): `VITE_API_BASE_URL` (default `/api/v1`), `VITE_MAP_TILE_URL` (default the public OpenStreetMap server, for light use only: set a provider before production and add its host to the CSP `img-src` in `frontend/nginx.conf.template`). Web container runtime: `API_UPSTREAM` (default `http://backend:8000`).

## 5. Local reproducible stack (no hosted resources)
```bash
cp .env.compose.example .env.compose      # set POSTGRES_PASSWORD and JWT_SECRET (never commit this file)
docker compose --env-file .env.compose up --build
# web: http://localhost:8080   api: http://localhost:8000   database: internal only
docker compose --env-file .env.compose down -v    # stop and delete the volumes
```
The stack has its own PostGIS container (created from `template0` so the first migration installs PostGIS into the `extensions` schema, exactly as on a hosted provider), a one-shot `migrate` service, the API and the web proxy. It never reads `backend/.env`, so it cannot touch the Supabase database, and your normal venv + Supabase workflow is unchanged. `bash ops/smoke-compose.sh` builds the stack and exercises it end to end (this is what CI runs).

## 6. Releasing
1. **Build** the images from a commit that passed CI and tag them with the commit SHA (never deploy `latest`).
2. **Back up** the database (BACKUP_RECOVERY.md). Mandatory before a migration that changes or drops data.
3. **Migrate**: run the `migrate` command once (`alembic upgrade head`) against the target database with the new image, before the new API starts. A failed migration stops the release; the old version keeps serving.
4. **Roll out** api, then web, then worker. Wait for each container's health check.
5. **Verify**: `/readyz` is 200; sign in; run `bash ops/smoke-compose.sh`-style checks against the environment; read the audit log for errors.
6. Keep the previous image tags for rollback.

## 7. Migrations policy
Forward-only in shared environments. Make every migration **backward compatible with the previous release** (expand, then contract): add nullable columns and new tables first, deploy code that uses them, remove old columns only in a later release. This keeps step 3 safe while old containers are still running and makes rollback (section 8) possible. Migrations never run automatically at API start-up (several replicas would race). `alembic check` in CI proves the models and migrations agree; CI also proves `downgrade base` then `upgrade head` works on an empty database.

## 8. Health, monitoring and rollback
- **Liveness**: `GET /healthz` (process is up; used by the container health checks). **Readiness**: `GET /readyz` (also checks the database; use it for load balancer routing).
- **Logs**: one JSON line per request (`request` event with status, duration, client address, `request_id`); errors include the request ID that the user sees. Ship stdout to the platform's log service; alert on `status >= 500` rate, `unhandled_exception` events, `auth.login.locked` audit events and `access.denied` bursts.
- **Application rollback**: redeploy the previous image tag. Safe when the migration was backward compatible.
- **Database rollback**: prefer rolling forward with a fix. `alembic downgrade` is for development and staging. In production, if data was damaged, restore from backup (BACKUP_RECOVERY.md); a downgrade can drop data.
- **Secrets rotation**: changing `JWT_SECRET` signs everyone out (access tokens become invalid); refresh tokens are hashed in the database and are unaffected by the secret but a rotated secret forces re-login at the next refresh only if you also revoke them.

## 9. Evidence storage in a real deployment
Photos are written through the `ObjectStore` interface. The only production-capable adapter today writes to a directory, so:
- **One API instance** with a durable volume mounted at `/data/storage` works.
- **Several API instances** need a shared filesystem or the S3-compatible adapter (`STORAGE_PROVIDER=s3`, built; see STAGING.md and STORAGE_REVIEW.md; verified against a simulated S3 only, never a real bucket).
Include the storage volume in backups (`EVIDENCE_DIR` in `ops/backup.sh`).

**Orphan blobs.** An upload writes the blob before the database row, so a crash in between (or a failed compensating delete) can leave an object nothing points to. `python -m app.tools.evidence_reconcile` lists them (dry run by default); `--delete` removes only objects with a server-shaped key, no evidence row (soft-deleted rows count as references), older than `--min-age-hours` (default 24, never below 1), and refuses when the database has no evidence rows or more than 20% of objects look orphaned. Point it at the SAME environment as the API (same `DATABASE_URL` and `STORAGE_*`), run the dry run first, and read the report. It is not scheduled by the worker. Soft-deleted evidence keeps its blob until a retention policy exists. A missing object normally answers 404; with a credential that cannot list the bucket some providers answer 403, which the API reports as 503 (permissions are not broadened to hide this).

## 10. The worker (Stage C, ADR-039)
`python -m app.worker` from the same image, as its own service (`worker` in `docker-compose.yml`). Every `WORKER_POLL_INTERVAL_S` it runs the agent for each workspace that is due (default: once a day per workspace; per workspace `settings.agent.schedule_enabled` and `schedule_interval_hours`), fails runs abandoned by a dead worker, and every `HOUSEKEEPING_INTERVAL_S` runs the housekeeping job (audit retention, idle throttle counters; `python -m app.tools.housekeeping` still works on its own).
- **No queue, no extra service.** The schedule is the `agent_runs` table: restarting or duplicating the worker is safe. A partial unique index allows one running run per workspace, so a manual run, a scheduled run and a second worker never overlap.
- **Failures** roll back the whole evaluation, are recorded in the run history with a short redacted reason and an audit event, and are retried after 5 minutes, doubling per consecutive failure but never beyond the normal interval. One failing workspace does not stop the others.
- **Shutdown:** SIGTERM/SIGINT let the run in progress finish, then the process exits 0 (`stop_grace_period: 60s` in compose; give your platform at least as long).
- **Health:** `python -m app.worker --healthcheck` exits 0 while the heartbeat file (`WORKER_HEARTBEAT_FILE`, default in the temp directory) is fresh. It proves the loop is alive, not that the database or the weather provider is reachable; alert on `agent_run_failed` log events and `agent.run` audit events with outcome `failure`.
- **Weather:** requested only for assets that have an open watering task, one request per ~11 km grid cell per run; nothing is requested when the irrigation rule is switched off. With `WEATHER_PROVIDER=open_meteo` the worker makes outbound HTTPS calls; open the egress if you restrict it. Open-Meteo's free tier is non-commercial (R-WX-1).
- `--once` runs a single pass and exits, for cron-style platforms.

## 11. Go-live checklist
TLS at the edge with HSTS; `ENV=production`; unique `JWT_SECRET` from a secret store; `TRUSTED_PROXY_COUNT` matches the proxy chain; `CORS_ORIGINS` is the real origin only; database TLS verified; backups scheduled and one restore rehearsed; storage durable; tile provider chosen and in the CSP; weather licence decided; log shipping and alerts on; `SECURITY.md` open items reviewed (email verification, password reset); a named person owns the on-call and the backup schedule.

## 12. What is verified, and what is not
| Claim | Evidence |
|---|---|
| Images build, run as non-root, hold no secrets, start without root; compose stack serves the app through nginx; registration, login, a located asset, the PostGIS map query, a photo upload and byte-exact download work through the proxy; migrations apply in a PostGIS container | `ops/smoke-compose.sh`, run by CI job `containers` (passed in run 39070024954; 29 checks, including the worker: healthy heartbeat, a scheduled run recorded, uid 10001, exit 0 on SIGTERM) |
| Dockerfiles pass hadolint; images have no HIGH/CRITICAL fixable vulnerabilities | CI job `containers` (Trivy 0.76.0; the first web base image failed this gate with 41 findings and was replaced) |
| The production Content-Security-Policy does not break the app (login, map with tiles, uploads, blob images, viewer) | checked by hand in a real browser against the production build and the exact header from `nginx.conf.template` |
| Not verified: running the containers on your machine (no Docker installed here), any real hosting provider, TLS termination, S3 storage (not built), multi-replica behaviour, load |  |

Base images: `python:3.12-slim-bookworm`, `node:22-alpine` (build only) and `nginxinc/nginx-unprivileged:1.30-alpine` track a minor version, not a digest. Rebuild and redeploy regularly (at least monthly, immediately for a scanner finding) to pick up OS patches; CI's Trivy gate fails the build when a base image becomes too old.
