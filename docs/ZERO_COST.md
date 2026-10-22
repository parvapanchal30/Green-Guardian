# Zero-cost deployment design (2026-10-22)

_Status: **design and verification of provider terms only. Nothing was provisioned, deployed or paid for.** Budget: ₹0 / $0, no paid trials, no card-backed services, no purchased domain. This document supersedes the paid options in [STAGING.md](STAGING.md) section 2 for as long as that budget holds; the rest of STAGING.md (topology rules, code-readiness audit, checklist) still applies. Every figure below was read from the provider's own documentation on 2026-10-22 unless marked **unverified**. Free tiers change; re-read before relying on them._

## 1. Summary
| Component | Zero-cost choice | Honest status |
|---|---|---|
| Frontend | **Vercel Hobby** (project exists) | Free, but **non-commercial personal use only** |
| API (FastAPI) | **Vercel Functions on Hobby** (a second Vercel project, Python runtime) | Free and on an account that already exists; needs small code changes and **a 4.5 MB request-body cap**. Not "always on": cold starts |
| Worker | **No free always-on host was found.** Closest compromise: a **daily Vercel Cron** that calls an authenticated tick endpoint, plus the existing manual `POST /agent/run` | Compromise, not equivalent. GitHub Actions is **not recommended** for production work (terms, section 4) |
| Database | **Existing Supabase project** (Free plan, 23 MB of 500 MB used) | Free; **paused after 1 week of inactivity**; **no backups** on Free |
| Staging database | **A second Supabase project in the same free organization** (the tool quotes $0/month) | Fits the 2-active-project limit only while the unrelated *Cafe Commune* project stays paused. Not created |
| Evidence storage | **Supabase Storage S3 endpoint** (1 GB, 50 MB per object on Free) | S3 availability **on the Free plan is unverified**; compatibility with our adapter is unverified against the real service |
| Domain | Free provider subdomains (`*.vercel.app`) | |
| Alerts, errors | Provider dashboards and logs only | No error-reporting service; Vercel Hobby keeps 1 hour of runtime logs |

If any of these facts changes (or the project becomes commercial), the design falls back to the paid options in STAGING.md.

## 2. Component by component

### 2.1 Frontend: Vercel Hobby
- **Allowance:** 100 GB Fast Data Transfer, 10 GB Fast Origin Transfer, 1,000,000 CDN requests per month; 200 projects; 100 deployments per day; 50 domains per project. Over a limit you wait 30 days (Hobby is not billed).
- **Restriction that matters:** "Hobby teams are restricted to non-commercial personal use only." Commercial use means a deployment used for the financial gain of anyone involved in producing it, including a paid employee or consultant writing the code, requesting or processing payment, advertising a product or service for sale, or receiving payment to create, update or host the site. Donations do not count. **Decision for you:** a college or portfolio project fits; a product you charge for, or a client engagement, does not.
- Sleep/cold start: none (static CDN). Persistence: n/a. Region: global CDN.
- Account: exists (`greenguardian-web`, Vercel Authentication on). External dependency: yes (Vercel). Git connection: **not verified**.

### 2.2 API: Vercel Functions (Hobby), second project
- **Fit:** FastAPI is supported with the Python runtime; lifespan start-up/shutdown is supported (shutdown cleanup is limited to 500 ms after SIGTERM, which the pool release in `lifespan` fits).
- **Allowance and limits (Hobby):** 1,000,000 invocations, 4 CPU-hours Active CPU and 360 GB-hours provisioned memory per month; 2 GB memory / 1 vCPU; **300 s maximum duration**; **4.5 MB maximum request or response body (413 beyond it)**; 500 MB Python bundle (our production dependencies measure about 82 MB installed, plus about 20 MB for the S3 client: **estimate**); 1,024 file descriptors shared across concurrent executions; **single region** (default `iad1`; the Seoul region id must be confirmed on Vercel's region list: **unverified**); runtime logs kept 1 hour.
- **Consequences for our code (none implemented yet):**
  1. **Uploads:** our default cap is 10 MB; on Vercel set `STORAGE_MAX_BYTES` to about 4,000,000 and resize photos in the browser before upload. A direct-to-storage upload (presigned) would lift the limit but changes the security model (ADR-052 rejects it for now).
  2. **No local disk:** `STORAGE_PROVIDER=s3` is mandatory (section 2.5).
  3. **Database connections:** use the Supabase **transaction pooler** (port 6543) with `DB_POOL_MODE=transaction`, a small pool, `pool_pre_ping`. Direct connections are IPv6-only on Supabase; poolers are the IPv4-compatible route.
  4. **Entrypoint:** Vercel looks for a module-level `app`; ours is a factory, so a one-line shim module is needed.
  5. **Cold start:** importing the app takes about 1.7 s on this machine with a warm disk cache; the Vercel cold start was **not measured**.
  6. **Protection:** the API project must **not** have Vercel Authentication on its API alias or the browser's cross-origin calls would be blocked; the API is protected by its own JWT authentication, CORS and tenant isolation. That makes it publicly reachable, which needs your explicit authorization.
  7. **Latency:** if the function runs in `iad1` and the database in Seoul, every query pays an ocean crossing. Choose the region nearest Seoul.
- **Availability:** no always-on process, no persistent disk, no background threads that outlive a request.
- **Commercial use:** same Hobby restriction. Account: exists. Dependency: Vercel (shared with the frontend, so it is one vendor, but also one outage domain).

### 2.3 Worker (Botanical Operations): no free always-on option
Always-on free hosting was checked and **does not exist among the options verified here**:
| Option | Verified outcome |
|---|---|
| Render free web service | Web services only (no background worker on the free tier); spins down after 15 minutes idle (about one minute to wake); 750 free hours per month; no persistent disk; "Do not use them for production applications." Unclear whether a payment method is needed (**unverified**) |
| Hugging Face Docker Spaces | "Gradio and Docker Spaces run on compute and require a paid plan to create" |
| Koyeb | The pricing page lists no free compute instance (only a free serverless Postgres) |
| Google Cloud Run | Terms page could not be read; Cloud Billing account (a card) is believed to be required: **unverified**, so excluded under a no-card budget |
| Fly.io, Railway | Paid (usage or monthly fee) |
| Vercel Functions | Not an always-on process (see 2.2) |

**Closest zero-cost compromise:** run the agent **on demand and once a day**:
- A Vercel Cron entry (Hobby: **once per day**, fired anywhere within the scheduled hour, ±59 minutes; up to 100 cron jobs) calls an internal endpoint that performs one `scheduler.tick` (the same code path as `python -m app.worker --once`).
- The worker already tolerates this: state is only in the database, a partial unique index prevents overlapping runs, failed runs retry with backoff on the next tick, abandoned runs are reaped.
- **Known interaction:** the default schedule interval is 24 hours, so a cron that drifts earlier by even a few minutes finds the previous run "not yet due" and skips a whole day. The tick endpoint must therefore treat a workspace as due with a tolerance (for example two hours) or the interval must be set to 20-22 hours.
- Users can also press "run now" (`POST /agent/run`, already built).
- Cron-triggered work is limited to the function's 300 s and the 4 CPU-hour monthly allowance; a few workspaces fit, many would not.
- **Endpoint security (to design before building):** disabled unless a `CRON_SECRET` is set; constant-time comparison; no tenant parameters; no response body beyond counts; rate-limited; documented in the tenancy matrix as a non-tenant route.

### 2.4 Database: existing Supabase project (Free plan)
Facts read from Supabase and from the project itself:
- **Plan:** the organization `parvapanchal` is on the **free** plan (tool-verified). Project `greenguardian`, region `ap-northeast-2` (Seoul), PostgreSQL 17. Measured: database size **23 MB** of the 500 MB per-project limit; **60** maximum connections, 13 in use (read-only queries only; nothing was changed).
- **Free plan allowances:** 2 active projects (paused projects do not count; the limit is across all organizations you own or administer), 500 MB database, 1 GB file storage, **50 MB** maximum upload, 5 GB egress plus 5 GB cached egress, 50,000 monthly active users, shared CPU with 500 MB RAM.
- **Constraints:** projects are **paused after 1 week of inactivity** (restoring is manual; what counts as activity is not officially defined; reports suggest real queries do, a bare connection may not: **unverified**); **no automatic backups or point-in-time recovery**; no branching; no log drains; no uptime SLA. Supabase's pricing page says nothing about commercial use of the Free plan: **check the Terms of Service** before any commercial use.
- **Backups at zero cost:** `ops/backup.sh` produces dumps; store them **outside Git and CI artifacts** (the repository is public), for example encrypted on your own disk. The database is 23 MB, so this is cheap. A restore rehearsal is still outstanding.
- **Connectivity:** direct connections are IPv6-only; poolers (Supavisor) work over IPv4. The paid IPv4 add-on is not needed if poolers are used.

### 2.5 Evidence storage: Supabase Storage (S3 protocol)
- **Why this one:** same account and project family, no new vendor; our S3 adapter takes any endpoint. The compatibility page lists PutObject, GetObject, HeadObject, DeleteObject and ListObjectsV2 as supported; Content-MD5 is not supported on PutObject (we do not send it; the adapter sets checksums to "when required"); **versioning is not supported and deletions are permanent**; you must enable the S3 connection in Storage Settings.
- **Allowance (Free plan):** 1 GB storage, 50 MB per object, egress counted against the 5 GB egress allowance (our API proxies every read, so image views count). At 4 MB per photo, 1 GB is on the order of 250 photos at full size, more after resizing: **plan for resizing**.
- **Unverified:** that the S3 endpoint is available on the Free plan (the compatibility page does not say); the exact endpoint and region value; behaviour of our adapter against the real service. `python -m app.tools.storage_check` is the test, to be run only after you approve creating the bucket.
- **Isolation:** Supabase S3 access keys are project-wide and bypass Storage policies (third-party documentation): treat them as a server secret, and use the **separate staging project** so a staging key cannot reach production objects.
- **Cloudflare R2 (not recommended under this budget):** documented free tier of 10 GB-month, 1 million Class A and 10 million Class B operations per month, free egress, **but** enabling needs "a Cloudflare account with an R2 subscription" through a checkout flow, and the documentation does not say whether a card is required: **unverified**. Do not use it until that is verified.

### 2.6 Domain, TLS, secrets
Free `*.vercel.app` subdomains with managed TLS; no domain is bought. Secrets live in each Vercel project's environment variables (marked sensitive) and in GitHub Actions secrets only where a workflow needs them; never in Git.

## 3. Staging within the free allowance
- **True production-like staging is possible at $0** with a **second Supabase project** in the same free organization: the pricing tool quotes **$0 per month** for a new project, and the 2-active-project rule is met while *Cafe Commune* (unrelated, currently paused) stays paused. It has its own database, pooler credentials and JWT secret, a separate Storage project (so separate S3 keys), and a separate Vercel API project and frontend Preview. Costs/risks: it also pauses after a week idle, has no backups and no support beyond the community, and restoring *Cafe Commune* would break the 2-project rule. **Not created** (needs your approval).
- **Closest alternative if you decline a second project (not true staging):** a throwaway schema in the existing project, as the test suite already does (`gg_test_*`). It shares credentials, pooler, connection budget (60) and JWT secret with the only real database, so it is a *testing* environment, never a staging environment; do not point a deployed preview at it.
- No migration was run against any database in this task.

## 4. GitHub Actions for scheduled operations
**Technical viability.** The worker is well suited to a one-shot run: `python -m app.worker --once` does one pass (scheduler tick + housekeeping) and exits; state is in the database; a partial unique index allows only one `running` run per workspace; failures back off and retry on later ticks; abandoned runs are reaped after `AGENT_STALE_RUN_S`; SIGINT/SIGTERM finish the run in progress. A job that is cancelled or times out leaves at worst a `running` row that the next pass reaps.

**Constraints verified:**
- Scheduled workflows run **only on the default branch** (currently `ci/first-run`), at most every **5 minutes**, in UTC, can be **delayed or dropped under load**, and in a **public repository are disabled after 60 days without repository activity**.
- Standard GitHub-hosted runners are free for public repositories (no quota stated).
- Runners are **IPv4-only**, so the job must connect through a Supabase pooler, not the direct connection; the database password would live in an Actions secret.
- **Terms:** for GitHub-hosted runners, Actions "should not be used" for "any other activity unrelated to the production, testing, deployment, or publication of the software project", and GitHub's terms name "as part of a serverless application" as an example of undue burden. Running **the application's real scheduled operations** is not obviously production, testing or deployment *of the software*; it is at best a gray area and at worst a violation that can get the workflow or account restricted.

**Verdict.** Technically feasible, **not recommended as the production worker host** because of the terms risk, schedule unreliability and the 60-day shutdown. It is reasonable as a **test**: a scheduled or manual workflow that runs `--once` against the *staging* database to prove the worker still works (that is "testing"). If you ever want it, the safe shape is: `schedule` plus `workflow_dispatch`; `concurrency: { group: worker, cancel-in-progress: false }`; `timeout-minutes: 10`; `permissions: contents: read`; secrets via a protected GitHub **Environment**; the pooler URL only; `if: github.repository == 'parvapanchal30/Green-Guardian'`; logs without secrets; the outcome is already recorded in `agent_runs`. **No workflow was added**, to avoid claiming the worker is hosted.

## 5. Vercel preview, without an API
- Vercel previews need a valid, non-reserved **https API URL** (the guard stays). A protected **static-shell** review is therefore done **locally**: `npm run build` then `npm run preview` in `frontend/` (no deployment, no cost), clearly labelled as a shell with no backend.
- A deployed Preview becomes possible after the API exists as a Vercel project (its `*.vercel.app` alias is a real https URL). Order: API project, then set Preview `VITE_API_BASE_URL`, then deploy a Preview, then verify.
- Preconditions before any Vercel deployment: Git integration verified, real API URL set, target explicitly Preview, and the Production branch decided (HOSTING.md section 5a).

## 6. What remains unverified
1. Vercel Git connection and the cause of `git_info_fail` (team-scope grant declined).
2. Vercel function region id for Seoul, real cold-start time and behaviour of this app on the Python runtime.
3. Supabase S3 availability on Free, endpoint and region value; adapter behaviour on the real service.
4. What counts as "activity" against Supabase's 1-week pause; Supabase Terms for commercial use of Free.
5. Whether Render's free tier needs a card (not used here), Cloud Run's billing requirement, R2's payment requirement.
6. Supabase Cron (`pg_cron`) availability on Free: documented as supporting HTTP calls, plan availability not stated. If available it could call the tick endpoint more often than Vercel's daily cron; verify before relying on it.

## 7. Dependencies introduced by this design
Vercel (frontend, API, cron), Supabase (database, storage), GitHub (source, CI). Three vendors, all already in use. A failure or a policy change at Vercel takes the frontend, API and cron down together.

## 8. Sources (official, read 2026-10-22)
- Vercel: [Hobby plan](https://vercel.com/docs/plans/hobby), [Functions limits](https://vercel.com/docs/functions/limitations), [Fair use guidelines](https://vercel.com/docs/limits/fair-use-guidelines), [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi), [Function regions](https://vercel.com/docs/functions/configuring-functions/region), [Cron jobs usage](https://vercel.com/docs/cron-jobs/usage-and-pricing)
- Supabase: [Pricing](https://supabase.com/pricing), [Billing](https://supabase.com/docs/guides/platform/billing-on-supabase), [IPv4/IPv6](https://supabase.com/docs/guides/troubleshooting/supabase--your-network-ipv4-and-ipv6-compatibility-cHe3BP), [S3 compatibility](https://supabase.com/docs/guides/storage/s3/compatibility), [Cron](https://supabase.com/docs/guides/cron)
- GitHub: [Events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows), [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [Terms for additional products](https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features)
- Others: [Render free instances](https://render.com/docs/free), [Hugging Face Spaces](https://huggingface.co/docs/hub/spaces-overview), [Koyeb pricing](https://www.koyeb.com/pricing), [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/), [R2 get started](https://developers.cloudflare.com/r2/get-started/)
