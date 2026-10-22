# Hosting GreenGuardian: Vercel for the frontend, a container host for the API and worker

_Status 2026-10-18. **Nothing is deployed.** The frontend is configured for Vercel and verified locally and in CI; a Vercel project exists but has no successful deployment (see section 5). The API and worker have no host yet. Names of variables appear here; values never do._

> Staging design, hosting options and the code-readiness audit: [STAGING.md](STAGING.md). **Zero-cost constraint (₹0 budget), verified free-tier limits and the Hobby non-commercial restriction: [ZERO_COST.md](ZERO_COST.md).** Review of the S3 adapter: [STORAGE_REVIEW.md](STORAGE_REVIEW.md).

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
| `VITE_API_BASE_URL` | public | `https://<api-host>/api/v1` (Production environment; currently **unset** on purpose) | the **staging** API, never production (Preview environment; currently a `.invalid` placeholder that **fails the build**) | absolute https URL of the API. Build fails if missing, not https, local, a reserved placeholder host or carrying credentials. Environments: Production, Preview (Development unused). |
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
| `STORAGE_S3_BUCKET`, `STORAGE_S3_REGION`, `STORAGE_S3_ENDPOINT_URL`, `STORAGE_S3_PREFIX`, `STORAGE_S3_PATH_STYLE`, `STORAGE_S3_TIMEOUT_S`, `STORAGE_S3_MAX_ATTEMPTS` | no | with `STORAGE_PROVIDER=s3`; one private bucket per environment. |
| `STORAGE_S3_ACCESS_KEY_ID`, `STORAGE_S3_SECRET_ACCESS_KEY` | **secret** | both or neither (neither = the platform's role); credentials limited to the one bucket. |
| `WEATHER_PROVIDER`, `OPEN_METEO_BASE_URL`, `WEATHER_TIMEOUT_S`, `WEATHER_CACHE_TTL_S` | no | Open-Meteo's free tier is non-commercial (R-WX-1). |
| `AUDIT_RETENTION_DAYS`, `AUDIT_DENIED_DEDUPE_S`, `LOG_LEVEL` | no | |
| `WORKER_POLL_INTERVAL_S`, `AGENT_STALE_RUN_S`, `HOUSEKEEPING_INTERVAL_S`, `WORKER_HEARTBEAT_FILE` | no | worker only. |

Development, staging and production use **separate** databases (or Supabase branches), separate `JWT_SECRET`s and separate hosts. A preview frontend must never be built against the production API, and the preview API must never hold production data.

## 5. What was done and what was verified
| Level | Status |
|---|---|
| **Local validation** | Done (re-run 2026-10-22, 161 frontend tests, type-check, lint, build): hosted-style builds fail with no API URL, an `http://` URL, a localhost URL and a `.invalid` URL, and pass with a real-looking https URL; `verify:dist` passes; the CSP names exactly the API origin; 26 frontend tests cover the guard, the CSP, `vercel.json` and the post-build check (including crafted bad bundles). |
| **CI** | The hosted-style build step runs on every push (see CURRENT_STATE for the run). |
| **Vercel project** | A project `greenguardian-web` was created on the free Hobby plan (root `frontend`, Vite, **Vercel Authentication enabled for all deployments**, `VITE_API_BASE_URL` set for the *preview* environment only, to a reserved `.invalid` placeholder). |
| **Preview deployment** | **Not deployed.** The one attempt (from the GitHub commit) failed immediately with `git_info_fail`: the Vercel account has **no GitHub connection**, and no Vercel CLI or login exists on the development machine. The build never ran and nothing is live. |
| **Production deployment** | None. The production environment has no API URL, so a production build would fail the guard, by design. |
| **Verified on a deployed URL** | Nothing: direct-route refresh, headers, console/network behaviour, frontend-to-API connectivity, authentication and protected endpoints are **unverified** until a preview exists and an API is reachable. |

Because the repository's default branch is currently `ci/first-run`, **Vercel treats a deployment of that branch as Production**. Before connecting Git, set the project's production branch to a release branch you control, or the first deploy of this feature branch will target production.

### 5a. Readiness review of 2026-10-22 (what was inspected, and what it showed)
**Vercel project (read through the authorised project tools).** `greenguardian-web`, framework Vite, Node setting 24.x (the `engines.node = 22.x` in `frontend/package.json` takes precedence for builds; both are supported, CI uses 22), Vercel Authentication on for **all** deployments, no password or IP rules, `live: false`, one deployment in state ERROR (`git_info_fail`, target production, built from commit `f905a46`), one environment variable (`VITE_API_BASE_URL`, **Preview only**, a `.invalid` placeholder). The project belongs to a **team scope** (`parvampanchal`), not only the personal account.

**What could not be verified, and why.**
- *GitHub integration:* the project tools expose no Git-link field, the GitHub namespace listing is empty and the integration-configuration listing is empty. That is consistent with "no GitHub connection" but is **not proof**. The `git_info_fail` reason could not be read: the deployment-event/log call returned 403 because this tool connection has no grant for the team scope, and the grant request (`authorize_team_access`) was declined in this session. **Do not create a second GitHub App**; first check Settings > Git in the dashboard (below).
- *Production branch setting:* shown as `ci/first-run` in the dashboard per the owner; not readable through the tools, and **not changed**.
- *Preview protection:* `ssoProtection = all` means previews require a Vercel login (verified from the project record, not from a deployed URL).

**Production-branch evidence (git).** The remote has exactly one branch, `ci/first-run`, which is also the GitHub default. A local `main` exists but is **not on the remote**, is **51 commits behind** `ci/first-run` and contains none of the Vercel files, hosting guards or Stage C/D work. Naming `main` the production branch would therefore deploy an obsolete tree (or fail). Recommendation, **not applied**: keep `ci/first-run` as the integration branch, create a dedicated release branch (for example `release`) only when you decide to ship, and set it as the Vercel Production Branch; every other branch, including `ci/first-run`, then produces Preview deployments. Merging into `main` was not done and is not needed for this.

**Changes made in this review.** (1) The build guard now also **rejects reserved placeholder hosts** (`.invalid`, `.localhost`, `.local`), so a build can never "succeed" against an API that cannot exist; (2) `verify:dist` fails if a `.invalid` URL is in the built bundle. Consequence: **the current Preview value of `VITE_API_BASE_URL` (a `.invalid` placeholder) now makes every Vercel preview build fail with a clear message.** That is intended: nothing may look like a working API before one exists. It must be replaced by the real staging API URL (section 9) before the first preview.

**CSP review.** Directives: `default-src 'self'`; `script-src 'self'` (no inline or eval; the Vite bundle is external); `style-src 'self' 'unsafe-inline'` (Leaflet positions map tiles with inline styles; accepted and documented, scripts stay strict); `img-src 'self' data: blob:` plus the tile host(s); `connect-src 'self'` plus exactly the API origin; `object-src 'none'`; `base-uri`/`form-action 'self'`. The only third-party fetch in the source is the map tile server (`AssetMap.tsx`); the openstreetmap.org attribution is a link, not a request. Not weakened. Note: Vercel's preview "comments toolbar" injects a script from `vercel.live`; this CSP blocks it and the browser console will show that violation on preview URLs. Do not add `vercel.live` to silence it; turn the toolbar off in the project settings if the noise matters.

**Preview gate (brief section 5).** A preview was **not** attempted: (a) the Git connection is unverified and the one prior attempt failed; (b) the Preview API URL is a non-working placeholder and the build correctly refuses it; (c) no API is hosted, so nothing could be verified end to end anyway. Nothing was deployed to Production, no domain was assigned, no resource was created.

**Can a preview be built safely before the backend is hosted?** Not honestly, by design. A hosted build needs a real https API URL. Two acceptable routes: (1) host a **staging API** first (preferred; section 9), then set Preview `VITE_API_BASE_URL` to it; or (2) deliberately build a *static shell* preview against a real but empty/unreachable staging hostname you own, accepting that every API call fails: this exercises routing, headers and CSP only, must be labelled as such, and still requires a valid, non-reserved https URL.

## 6. Storage for uploads
Local filesystem uploads are acceptable only on a single API instance with a **persistent volume** (mount at `/data/storage`; back it up with the database). Several instances, or any host with ephemeral disks, use the **S3-compatible adapter** (`STORAGE_PROVIDER=s3`, built 2026-10-22, ADR-052): a private bucket, API-proxied reads after the workspace check, no presigned or public URLs. It is verified against a simulated S3 only; **no real bucket exists or was contacted**, and the provider is not chosen. See [STAGING.md](STAGING.md) sections 4 and 6.

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
1. **Check the Git connection** (dashboard > team `parvampanchal` > project `greenguardian-web` > Settings > Git). If "Connected Git Repository" shows `parvapanchal30/Green-Guardian`, the link exists and the earlier failure needs the deployment's build log (Deployments > the ERROR row > Build Logs; or grant this tool connection access to the team scope so it can read them). If it shows nothing: **Connect Git Repository**, choose GitHub, and install/authorise the Vercel GitHub App for that repository (GitHub > Settings > Applications > Vercel > Configure > Repository access). Use the existing app; do not create another. Alternatively install the Vercel CLI and sign in.
2. **Production branch** (Settings > Environments > Production > Branch Tracking): create a release branch first (section 5a), then set it here. Leave `ci/first-run` and every other branch as Preview. Until then a push to `ci/first-run` targets Production (which fails the API-URL guard, by design, because Production has no API URL).
2a. **Replace the Preview `VITE_API_BASE_URL` placeholder** (Settings > Environment Variables, Preview only) with the real staging API URL once it exists. The `.invalid` value now fails the build on purpose.
3. **Choose and pay for (or pick a free tier of) an API/worker host**, and approve creating it. Requirements: Docker, a secret store, persistent disk or object storage, health checks, graceful termination of at least 60 s, outbound HTTPS (Open-Meteo, Supabase), one always-on worker instance.
4. **Decide the domains**, and set `VITE_API_BASE_URL` (production and staging) and `CORS_ORIGINS` to the exact origins.
5. **Provide staging infrastructure** (a separate Supabase project or branch) so previews never touch production data.
6. Approve the weather-provider licensing position (R-WX-1) and the map tile provider before public use.

## 10. Go-live checklist (verification only counts when done on the deployed URLs)
Frontend preview deployed from the intended commit; direct visit and refresh of a deep link (for example `/w/<id>/ai/datasets`) returns the app, not a 404; `/api/...` and a missing `/assets/...` return real 404s from the right origin; response headers present; no CSP violations or console errors; the browser network panel shows requests going only to the configured API origin; sign-in works against the staging API; representative protected endpoints return 401 without a token and 200 with one; CORS preflight succeeds for the app origin and fails for another; worker heartbeat healthy and a scheduled run recorded; backups taken and one restore rehearsed; `SECURITY.md` open items reviewed; production promoted only on explicit approval.
