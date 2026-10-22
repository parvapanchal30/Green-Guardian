# Staging architecture (design, 2026-10-22)

> **Budget update:** the owner's budget is ₹0 / $0. The paid hosts compared in section 2 are kept for reference only; the zero-cost design, verified provider limits and the staging-within-free-tier analysis are in [ZERO_COST.md](ZERO_COST.md), which takes precedence. Sections 3-8 still describe the intended topology rules and the code-readiness audit.

_Status: **design only. Nothing in this document has been provisioned, deployed or paid for.** It turns the split in [HOSTING.md](HOSTING.md) (Vercel for the frontend, containers for the API and the worker, Supabase for the database) into a concrete staging environment, compares hosting options, and lists what the code needed (done) and still needs (open). Prices are indicative figures from public pages read on the date above and must be re-checked before any decision._

## 1. Target topology

```
 Vercel Preview (static SPA, Vercel Authentication on)
        │  HTTPS, exact-origin CORS (the stable branch alias, never a wildcard)
        ▼
 API container (FastAPI, port 8000, /healthz /readyz)  ──┐
 Worker container (python -m app.worker, always-on)     ─┤── TLS (sslmode=require) ──► STAGING Supabase project
        │                                                │                              (own database, own JWT secret)
        └── S3 API, private bucket, bucket-scoped key ──►  STAGING object-storage bucket
```

Rules that make it staging and not a second production:
- **A separate Supabase project** (not a schema in the existing project, not a branch of production data). The existing project `greenguardian` (region `ap-northeast-2`, Seoul) is the **development** database and must not be reused: it holds the only real data so far. Migrations are applied to staging with the same `alembic upgrade head`.
- **A separate `JWT_SECRET`**, a separate bucket with credentials that can reach only that bucket, separate host secrets. A staging token must be useless on any other environment.
- `ENV=production` on staging too, so the production guards (exact https CORS origins, database TLS, no mock providers) apply there.
- The Vercel **Preview** environment's `VITE_API_BASE_URL` points at the staging API; the Production environment stays unset until production exists.
- Staging holds synthetic or consented test data only (no real customer data, no dataset downloads).

## 2. Hosting options for the API and the worker

All options run the repository's existing image (`backend/Dockerfile`; the worker is the same image with `python -m app.worker`). Criteria: always-on worker, cost, operational effort, region and compatibility. Figures are indicative.

| Option | Always-on worker | Indicative cost (staging: API + worker) | Operational effort | Region fit (database is in Seoul) | Notes |
|---|---|---|---|---|---|
| **Render** (web service + background worker) | Yes, a first-class "Background Worker" | Starter instances about $7/month each (512 MB, 0.5 CPU), so about **$14/month**; workers have no free tier; a free web service spins down after about 15 minutes idle (unsuitable for a worker, tolerable only for a throwaway API) | **Lowest**: Git or image deploys, dashboard, managed TLS, secret groups | Nearest listed region to Seoul is probably Singapore (verify) | Persistent disk is a paid add-on; the S3 adapter makes it unnecessary. Port must be set to 8000 |
| **Fly.io** | Yes (a Machine that is simply not stopped) | A shared-cpu-1x 256 MB Machine is about $1.94/month in Ashburn; the API likely needs 512 MB or more, so **roughly $5-12/month** for both, plus a volume at $0.15/GB if used | Medium: `flyctl`, a `fly.toml` with two process groups, secrets via CLI | Many regions including Tokyo (nearest to Seoul, verify) | Cheap and flexible; more to learn. Machine health checks are HTTP/TCP: the worker's file heartbeat needs a different probe (section 5) |
| **Railway** | Yes (a service with no public port) | Hobby $5/month including $5 of usage, then usage-based (RAM about $10/GB-month, CPU about $20/vCPU-month, volumes $0.15/GB-month); an idle-light API and worker may fit near **$5-10/month** | Low | Region list to verify | Usage billing is harder to predict; fine for staging |
| **Google Cloud Run** (API) + something else for the worker | API yes; the worker is **not natural**: it needs "CPU always allocated" and a minimum instance, which turns it into a continuously billed instance, or a VM | Pay per use for the API; a worker kept alive is not cheaper than the above | Higher (IAM, Artifact Registry, networking) | Seoul region exists | Strong later for the production API if scale-to-zero matters; poor fit for the polling worker |
| **One small VPS running the existing compose stack** (with a reverse proxy for TLS) | Yes | Lowest fixed monthly cost (not priced here) | **Highest**: you patch the OS, renew certificates, monitor, back up, roll back | Any | The compose file already works; closest to what CI exercises. Reasonable if cost matters more than operations time |

**Recommendation for staging (not applied):** **Render or Fly.io.** Pick Render if minimising operational effort matters (about $14/month, dashboard-driven); pick Fly.io if cost and region control matter and the CLI is acceptable. Either runs the unchanged image, supports an always-on worker with SIGTERM and a termination grace period, and keeps the existing Supabase database. Do not use Vercel Functions for the API or worker (HOSTING.md section 2). The decision needs your approval because both are paid services.

## 3. Staging components

| Component | Choice | Why |
|---|---|---|
| Frontend | Vercel Preview of a stable branch, alias used in `CORS_ORIGINS` | Preview URLs per deployment are not stable; allow only the branch alias |
| API | One container, `uvicorn app.main:create_app --factory --port 8000`, 1 instance | Local-disk evidence needs one instance; with the S3 adapter more can be added |
| Worker | One container, `python -m app.worker`, exactly one instance | A second worker is redundant but safe (section 4) |
| Database | New Supabase project, **session pooler or direct connection** for the API and worker; `DB_SSLMODE=require` or stricter | Long-lived processes with their own pool; the transaction pooler is for serverless and needs `DB_POOL_MODE=transaction` |
| Migrations | One-shot `alembic upgrade head` **release step before the new API/worker start**, over the direct or session connection (never the transaction pooler, never at API start-up) | Several replicas must not race each other on DDL |
| Evidence | S3-compatible **private** bucket via `STORAGE_PROVIDER=s3` (section 6) | Durable, host-independent, multi-instance safe |
| Backups | `ops/backup.sh` against the staging database on a schedule, stored outside Git and CI artifacts | The repository is public; dumps never go into it |
| Observability | JSON logs with request IDs to the host's log viewer; alerts on API 5xx, `unhandled_exception`, `agent_run_failed`, stale worker heartbeat, DB connection saturation | An error-reporting service is **not integrated yet** |
| Rollback | Redeploy the previous image tag (never `latest`); frontend via Vercel instant rollback; migrations are forward-only and backward compatible, so a rollback does not need a down-migration | |

## 4. Code readiness audit (what the code does today)

| Concern | State | Evidence |
|---|---|---|
| **Start-up** | Settings validated before serving; unknown weather/storage provider, missing JWT secret, unsafe production CORS, weak database TLS and (new) a missing S3 client library or invalid S3 settings stop the process at boot, not on first use | `core/config.py`, `main.py`; `test_core`, `test_storage_s3` |
| **Graceful shutdown** | API: uvicorn drains on SIGTERM; **new:** a lifespan hook now releases the database pool on shutdown. Worker: SIGTERM/SIGINT/SIGBREAK finish the run in progress, then exit | `main.py`, `worker.py`; `test_lifecycle`, `test_worker_process` |
| **Worker idempotency and duplicate runs** | Database-enforced: one running run per workspace (partial unique index), retries with backoff, stale-run reaper; a second worker is redundant, not harmful | ADR-039, `test_agent_runs`, `test_worker` |
| **Pooling and TLS** | `sslmode=require` by default; production refuses `disable/allow/prefer`; pool size, overflow, pre-ping and a transaction-pooler mode are configurable. **Budget connections:** (API instances + worker) x (pool + overflow) must stay below the Supabase plan's limit | `core/db.py`, `core/config.py` |
| **Migrations** | Alembic, forward-only; the image carries `alembic.ini` and `migrations/`; the Dockerfile says never to run them at start. **Open:** no advisory lock around `alembic upgrade`, so run it as a single release step | `Dockerfile`, compose `migrate` service |
| **Health and readiness** | API `/healthz` (process) and `/readyz` (database). Object-store health is deliberately **not** part of readiness: a storage outage already returns 503 `storage_unavailable` on uploads and image reads, and should not pull the whole API out of rotation. Probe the store with `python -m app.tools.storage_check` after provisioning. **Open:** the worker's health is a heartbeat *file* checked by exec (`python -m app.worker --healthcheck`); hosts that only offer HTTP/TCP checks for workers need a database-backed heartbeat or a tiny status endpoint (not built) | `main.py`, `worker.py` |
| **Durable storage and access control** | **New:** `S3ObjectStore` behind the existing `ObjectStore` port. The bucket is private and never exposed: every read goes through the API, which first checks workspace membership and role. Keys are server-generated and begin with the workspace id; **new:** a read refuses any row whose key is outside the caller's workspace prefix. No presigned or public URLs | `evidence/storage.py`, `evidence/service.py`; `test_storage_s3` |
| **Secrets** | Only from the environment; `.env.example` lists names; S3 keys are `SecretStr` (not shown by `repr` or serialisation) and are never in error text. The platform's secret store holds the values; prefer a role/identity over long-lived keys where the provider supports it | `core/config.py`; tests assert no leakage |
| **Separate staging and production configuration** | Same image, different environment. Nothing in the code can tell staging from production except `ENV` and the values supplied, so the separation is **operational**: distinct database URL, JWT secret, bucket and credentials per environment (a checklist, section 7) | |
| **Container port** | The image listens on 8000 and its `HEALTHCHECK` calls 127.0.0.1:8000; hosts that inject `$PORT` must be told to use 8000 | `Dockerfile` |
| **Not built** | S3 purge of soft-deleted evidence blobs (retained by design today); error-reporting integration; database heartbeat for the worker; object-store versioning/replication policy | TODO |

## 5. What was changed in the repository in this stage
1. `S3ObjectStore` + registry entry `s3` + validated `STORAGE_S3_*` settings (section 6).
2. Start-up check for the S3 client dependency; `s3` extra in `pyproject.toml`; the Dockerfile installs it; CI's `pip-audit` now audits it.
3. Tenant-prefix guard when serving evidence (defence in depth).
4. Database pool released on API shutdown (`dispose_engine`).
5. `python -m app.tools.storage_check`, an operator probe (put, get, compare, delete one throwaway object).
6. Tests: `test_storage_s3` (38, against a simulated S3 with `moto`; no network, no real credentials) and `test_lifecycle` (2). **Nothing was run against a real bucket.**

## 6. Object storage
Provider-neutral by design: any S3 API endpoint works with the same code. The choice of provider is **not made** (needs your decision); candidates:

| Provider | Fit | Caveats |
|---|---|---|
| **Supabase Storage (S3 protocol)** | Same vendor and project family as the database; S3 endpoint of the form `https://<project>.supabase.co/storage/v1/s3` | Its S3 access keys reach **all buckets of that project** and bypass Storage RLS: treat them as a server secret, and use a **separate Supabase project for staging** (which you need for the database anyway). Versioning is not supported; deleted objects are gone |
| **Cloudflare R2** | S3 API, no egress fees, free tier of about 10 GB-month (third-party figures) | Another vendor and account; set region `auto` |
| **AWS S3** | Most standard; IAM roles and bucket-scoped policies | Egress and request charges; account and IAM setup |
| **Backblaze B2 / MinIO** | S3 API | Not evaluated |

Configuration (names only, values in the host's secret store): `STORAGE_PROVIDER=s3`, `STORAGE_S3_BUCKET`, `STORAGE_S3_REGION`, `STORAGE_S3_ENDPOINT_URL` (empty for AWS), `STORAGE_S3_PREFIX` (optional), `STORAGE_S3_ACCESS_KEY_ID`, `STORAGE_S3_SECRET_ACCESS_KEY` (both, or neither to use a platform role), `STORAGE_S3_PATH_STYLE`, `STORAGE_S3_TIMEOUT_S`, `STORAGE_S3_MAX_ATTEMPTS`. Bucket requirements: **private (block public access)**, encryption at rest (provider default is acceptable), credentials limited to this one bucket and to get/put/delete/head objects, one bucket per environment.

## 7. Staging go-live checklist (order matters; every step needs your approval where it creates something)
1. Approve the host (section 2), the storage provider (section 6) and the staging database project. **Each may create a paid resource.**
2. Create the staging Supabase project; keep the existing project untouched. Record its region (prefer the same region as the host).
3. Create the private bucket and a bucket-scoped credential; run `python -m app.tools.storage_check` with the staging environment.
4. Set secrets on the host (names in section 6 and HOSTING.md section 4); `ENV=production`; `CORS_ORIGINS` = the Vercel branch alias only.
5. Run `alembic upgrade head` as a one-shot release step against the staging database; confirm `alembic check` reports no drift.
6. Start the API; confirm `/healthz` and `/readyz`; start exactly one worker; confirm the heartbeat and one recorded run.
7. Set the Vercel **Preview** `VITE_API_BASE_URL` to the staging API; deploy a Preview from a non-production branch.
8. Verify on the deployed URLs only: deep-link refresh, headers, console and network, sign-in, a protected endpoint (401 without a token, 200 with), CORS accepted for the alias and refused for another origin, an evidence upload and read-back, a worker run, a backup and a restore rehearsal.
9. Record the results in CURRENT_STATE as "preview-verified"; production is a separate decision.

## 8. Decisions that need you
1. API/worker host (Render, Fly.io, Railway, VPS or other) and its plan: paid.
2. Object-storage provider and whether staging gets its own Supabase project (a third project may exceed a free plan's project limit: unverified).
3. Region (the development database is in `ap-northeast-2`).
4. Staging domain/alias for the API and the frontend branch alias.
5. Who receives alerts, and which error-reporting service (if any).
6. The Vercel Git connection and the production branch (HOSTING.md section 5a).
