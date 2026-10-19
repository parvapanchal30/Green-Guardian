# Hosting GreenGuardian: Vercel for the frontend, a container host for the API and worker

_Status 2026-10-18. **Nothing is deployed.** The frontend is configured for Vercel and verified locally and in CI; a Vercel project exists but has no successful deployment (see section 5). The API and worker have no host yet. Names of variables appear here; values never do._

## 1. Decision
| Component | Where | Why |
|---|---|---|
| **Frontend** (React/Vite static build) | **Vercel** | A static single-page app is exactly what Vercel serves well: CDN, instant rollbacks, preview per branch. |
| **API** (FastAPI) | **A container host**, not Vercel Functions | See section 2: persistent database pool, evidence uploads that need durable storage, a long-lived process model and an audit/throttle design that assume one coherent service. |
| **Worker** (`python -m app.worker`) | **The same container host**, as its own always-on service | It is a long-running loop with graceful shutdown, a heartbeat and duplicate-run prevention. Vercel Functions are request-scoped. |
| **Database** | **Existing Supabase PostgreSQL 17 + PostGIS** (unchanged) | No migration or recreation as part of hosting. |
| **Evidence storage** | Persistent volume on the API host **or** an S3-compatible bucket (adapter not built yet) | Local disk of a serverless function does not persist. |

This is the topology the repository already supports: two images (`backend/Dockerfile`, `frontend/Dockerfile`) and a compose file. The frontend image stays useful for self-hosting; Vercel replaces only the static tier.

```
 Browser ──HTTPS──► Vercel (static SPA, CDN, security headers)
    │
    └──HTTPS, CORS for exactly the app origin──► API container (FastAPI, /healthz, /readyz)
                                                       │  TLS (sslmode=require)
                                         Worker container (same image) ──► Supabase PostgreSQL + PostGIS
                                                       │
                                            durable evidence storage (volume or S3-compatible)
```

## 2. Why the API and worker are not on Vercel (from the code and the Vercel documentation)
**Facts from the repository**
- The API is synchronous FastAPI + SQLAlchemy with a psycopg connection pool. A transaction-pooler mode exists (`DB_POOL_MODE=transaction`, no client pool, no server-side prepared statements), so a serverless deployment would be *possible* for ordinary requests.
- Evidence photos are written through `ObjectStore`; the only production-capable adapter writes to a local directory, and uploads may be up to `STORAGE_MAX_BYTES` (10 MB). A serverless function has no durable local disk.
- The worker (`app/worker.py`) is a polling loop: heartbeat file, SIGTERM handling that finishes the run in progress (the compose file allows 60 s), `--healthcheck`, a database-enforced one-running-run-per-workspace rule and stale-run recovery.
- Login throttling, audit and the agent history are in the database, so they would survive serverless, but the throttle's client-address logic needs `TRUSTED_PROXY_COUNT` to match the real proxy chain.

**Facts from Vercel's documentation (read in this session)**
- FastAPI runs on Vercel Functions, with `maxDuration` configurable per function (the API schema for project settings allows up to 900 s).
- For FastAPI lifespan shutdown, the documentation states that cleanup is limited to a maximum of 500 ms after SIGTERM. The worker needs seconds to finish a run; this alone rules the worker out.
- Background work in a function is `waitUntil` for the life of a request, not a standing process. Cron and queue features exist but would be a redesign of the scheduler, which today relies on a persistent loop and its heartbeat.
- **Not confirmed here:** Vercel's maximum request-body size for Functions. It is documented elsewhere as being in the low megabytes, which would be below the 10 MB upload limit; the documentation search in this session did not return the figure, so check it before reconsidering a serverless API.

**Conclusion.** The worker cannot sensibly run on Vercel. The API could run there for read-mostly traffic, but uploads, a per-instance database pool against a connection-limited Supabase plan, and one operational model for API and worker favour a container host. If a later requirement favours serverless, the API can move without changing the frontend (only `VITE_API_BASE_URL` and `CORS_ORIGINS`).

## 3. What the repository now provides for Vercel
| File | Purpose |
|---|---|
| `frontend/vercel.json` | install `npm ci`; build `npm run build && npm run verify:dist`; output `dist`; SPA rewrite for every path **except** `/api/`, `/assets/` and the favicon (so a missing API or asset is a real 404, not `index.html` with status 200); security headers; immutable caching for hashed assets, `no-cache` for `index.html`. |
| `frontend/package.json` | `engines.node = 22.x` (what CI and the Dockerfile use; Vercel reads it); `verify:dist` script. |
| `frontend/hosting.ts` + `vite.config.ts` | On any Vercel build the API URL must be an absolute `https` URL that is not local and has no credentials, or the build **fails**. Adds a Content-Security-Policy `<meta>` allowing the page and exactly that one API origin in `connect-src`. |
| `frontend/scripts/verify-dist.mjs` | After the build: no `localhost:port`, loopback or `0.0.0.0` anywhere in the bundle; the configured API URL is in the bundle; the CSP names exactly that origin and nothing broader. (react-router's bare `http://localhost` placeholder is allowed.) |
| `backend/app/core/config.py` | In `ENV=production` the API refuses to start with a wildcard, non-https, local, path-carrying or trailing-slash `CORS_ORIGINS` entry, or with database TLS disabled. |
| `.github/workflows/ci.yml` | A "hosted-style build and bundle verification" step runs the Vercel build commands on every push with a placeholder API URL. |

`VITE_*` variables are inlined into the public bundle: they hold only public values.

## 4. Environment variables (names only)
**Frontend (Vercel project settings; public by nature)**
| Name | Public/secret | Production | Preview | Purpose |
|---|---|---|---|---|
| `VITE_API_BASE_URL` | public | `https://<api-host>/api/v1` | the **staging** API, never production | absolute https URL of the API. Build fails if missing or unsafe. |
| `VITE_MAP_TILE_URL` | public | tile provider URL template | same | optional; the default is the public OpenStreetMap server (light use only); add the host to the CSP automatically. |
| `VERCEL`, `VERCEL_ENV` | system | set by Vercel | set by Vercel | switch on the build guard. |

**API and worker (the container host's secret store; same names as `backend/.env.example`)**
| Name | Secret? | Notes |
|---|---|---|
| `ENV` | no | `production` for production, staging included, so the guards apply. |
| `DATABASE_URL` | **secret** | Supabase connection string. Long-lived containers should use the **session** pooler (or the direct connection if IPv6 is available). `sslmode=require` or `DB_SSLMODE=require`/`verify-full`; production refuses anything weaker. |
| `DB_SCHEMA`, `POSTGIS_SCHEMA` | no | `greenguardian`, `extensions`. |
| `DB_POOL_MODE`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_CONNECT_TIMEOUT_S`, `DB_POOL_PRE_PING` | no | Size so that (API instances + worker) x (pool size + overflow) stays under the Supabase plan's connection limit. |
| `JWT_SECRET` | **secret** | 32+ characters, **different per environment** (a preview/staging token must never work on production). |
| `ACCESS_TOKEN_TTL_MINUTES`, `REFRESH_TOKEN_TTL_DAYS`, `AUTH_*` | no | token policy and throttling. |
| `CORS_ORIGINS` | no | JSON list of **exact** https origins, for example `["https://app.example.org"]`. No wildcard. A Vercel preview URL is generated per deployment, so allow only a stable alias (for example the branch alias) on the staging API. |
| `TRUSTED_PROXY_COUNT` | no | Number of reverse proxies in front of the API on that host (usually 1). Wrong values distort throttling and audit addresses. |
| `STORAGE_PROVIDER`, `STORAGE_LOCAL_DIR`, `STORAGE_MAX_BYTES`, `STORAGE_MAX_PIXELS` | no | see section 6. |
| `WEATHER_PROVIDER`, `OPEN_METEO_BASE_URL`, `WEATHER_TIMEOUT_S`, `WEATHER_CACHE_TTL_S` | no | Open-Meteo's free tier is non-commercial (R-WX-1). |
| `AUDIT_RETENTION_DAYS`, `AUDIT_DENIED_DEDUPE_S`, `LOG_LEVEL` | no | |
| `WORKER_POLL_INTERVAL_S`, `AGENT_STALE_RUN_S`, `HOUSEKEEPING_INTERVAL_S`, `WORKER_HEARTBEAT_FILE` | no | worker only. |

Development, staging and production use **separate** databases (or Supabase branches), separate `JWT_SECRET`s and separate hosts. A preview frontend must never be built against the production API, and the preview API must never hold production data.

## 5. What was done and what was verified
| Level | Status |
|---|---|
| **Local validation** | Done: hosted-style builds fail with no API URL and with an `http://localhost` URL, and pass with an https URL; `verify:dist` passes; the CSP names exactly the API origin; 26 frontend tests cover the guard, the CSP, `vercel.json` and the post-build check (including crafted bad bundles). |
| **CI** | The hosted-style build step runs on every push (see CURRENT_STATE for the run). |
| **Vercel project** | A project `greenguardian-web` was created on the free Hobby plan (root `frontend`, Vite, **Vercel Authentication enabled for all deployments**, `VITE_API_BASE_URL` set for the *preview* environment only, to a reserved `.invalid` placeholder). |
| **Preview deployment** | **Not deployed.** The one attempt (from the GitHub commit) failed immediately with `git_info_fail`: the Vercel account has **no GitHub connection**, and no Vercel CLI or login exists on the development machine. The build never ran and nothing is live. |
| **Production deployment** | None. The production environment has no API URL, so a production build would fail the guard, by design. |
| **Verified on a deployed URL** | Nothing: direct-route refresh, headers, console/network behaviour, frontend-to-API connectivity, authentication and protected endpoints are **unverified** until a preview exists and an API is reachable. |

Because the repository's default branch is currently `ci/first-run`, **Vercel treats a deployment of that branch as Production**. Before connecting Git, set the project's production branch to a release branch you control, or the first deploy of this feature branch will target production.

## 6. Storage for uploads
Local filesystem uploads are acceptable only on a single API instance with a **persistent volume** (mount at `/data/storage`; back it up with the database). Several instances, or any host with ephemeral disks, need an S3-compatible adapter, which is **not built** (the `ObjectStore` interface and registry are ready; it is one module and one dependency). Recommended next engineering step before a multi-instance deployment: an S3 adapter against an S3-compatible bucket, with presigned reads or API-proxied reads.

## 7. Authentication, tokens and CORS
Access tokens are Bearer tokens kept in memory; the refresh token is in `sessionStorage` (a known limitation, SECURITY.md). **No cookies are used**, so `allow_credentials` is false and cross-origin calls need only exact-origin CORS. Moving the refresh token to an httpOnly cookie later would require the app and API to share a site (for example `app.example.org` and `api.example.org`) and SameSite settings; plan for custom domains on one registrable domain. Rate limiting, lockout, audit and tenant isolation (workspace-scoped queries, composite foreign keys, RLS) live in the API and database and are unchanged by where the frontend is hosted.

## 8. Operations
- **Health:** API `GET /healthz` (process) and `GET /readyz` (database); worker `python -m app.worker --healthcheck` (heartbeat). Wire them to the host's checks.
- **Logs:** JSON lines with request IDs from API and worker; ship stdout to the host's log service. Vercel logs cover only the static tier.
- **Alerts to configure:** API 5xx rate, `unhandled_exception`, `agent_run_failed`, `access.denied` bursts, worker heartbeat stale, database connection saturation. **No error-reporting service is integrated yet.**
- **Backups:** the Supabase Free plan has none; use `ops/backup.sh` on a schedule (BACKUP_RECOVERY.md). No backup of the real database has been taken yet.
- **Rollback:** frontend: Vercel instant rollback / promote an earlier deployment. API and worker: redeploy the previous image tag (never `latest`). Database: migrations are forward-only and backward compatible (DEPLOYMENT.md section 7); never run a destructive migration against production without a fresh backup.
- **Build vs runtime:** the frontend's configuration is fixed **at build time** (a changed `VITE_*` value needs a rebuild); the API and worker read configuration at start.

## 9. Manual actions needed from you (nothing below was done)
1. **Connect GitHub to Vercel** (Vercel dashboard, project `greenguardian-web`, Settings, Git: connect `parvapanchal30/Green-Guardian`), or install the Vercel CLI and sign in on your machine. Without one of these no deployment can be created from here.
2. **Set the production branch** to a release branch (not `ci/first-run`) before the first Git-driven deployment.
3. **Choose and pay for (or pick a free tier of) an API/worker host**, and approve creating it. Requirements: Docker, a secret store, persistent disk or object storage, health checks, graceful termination of at least 60 s, outbound HTTPS (Open-Meteo, Supabase), one always-on worker instance.
4. **Decide the domains**, and set `VITE_API_BASE_URL` (production and staging) and `CORS_ORIGINS` to the exact origins.
5. **Provide staging infrastructure** (a separate Supabase project or branch) so previews never touch production data.
6. Approve the weather-provider licensing position (R-WX-1) and the map tile provider before public use.

## 10. Go-live checklist (verification only counts when done on the deployed URLs)
Frontend preview deployed from the intended commit; direct visit and refresh of a deep link (for example `/w/<id>/ai/datasets`) returns the app, not a 404; `/api/...` and a missing `/assets/...` return real 404s from the right origin; response headers present; no CSP violations or console errors; the browser network panel shows requests going only to the configured API origin; sign-in works against the staging API; representative protected endpoints return 401 without a token and 200 with one; CORS preflight succeeds for the app origin and fails for another; worker heartbeat healthy and a scheduled run recorded; backups taken and one restore rehearsed; `SECURITY.md` open items reviewed; production promoted only on explicit approval.
