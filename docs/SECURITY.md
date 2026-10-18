# Security

How GreenGuardian protects accounts, tenants and evidence, and where each control lives in the code. This describes what is implemented (verified by tests); open items are listed at the end. For database-level controls see `DATABASE_SETUP.md` section 9 (RLS) and ADR-023.

## Authentication
- Passwords: argon2id; an unknown email costs the same hashing time as a wrong password (no timing oracle).
- Access tokens: short-lived JWT (HS256). **`JWT_SECRET` must be at least 32 characters in every environment except tests**; the application refuses to start otherwise (an empty key would be unusable, a short one guessable).
- Refresh tokens: random, stored hashed, rotated on every use; presenting an already-used token is treated as theft and revokes every session of that user (and is recorded as a denied security event).

## Brute-force protection (`modules/identity/throttle.py`, ADR-032)
| Counter | Key | Default limit | Purpose |
|---|---|---|---|
| pair | this email + this address | 5 failures | stops guessing; an attacker can only lock their own pair |
| account | this email, any address | 15 failures | catches distributed guessing |
| address | any email from this address | 30 failures | catches password spraying |

Window 15 min, lockout 15 min, then counters start fresh (automatic recovery). Checked **before** the password is verified, so a locked caller learns nothing and costs no hashing. The attempt that crosses a limit still gets the normal 401; later attempts get **429 with `Retry-After`** and `retry_after_s`. A successful login clears the pair and account counters, never the address counter. Counters also protect `/auth/refresh` (invalid tokens, per address) and `/auth/register` (attempts, per address). State is in the database (`auth_throttle`), so it survives restarts and is shared by replicas. Keys hold a SHA-256 of the submitted email, never the address itself, and unknown emails throttle exactly like real ones (no account enumeration). Limits are settings (`AUTH_*`). Residual risk: registration still reveals whether an email is taken (409), which is limited by the per-address registration cap.

## Client address and request IDs (`core/request_context.py`, `core/middleware.py`, ADR-033)
- The client address is the socket peer. `X-Forwarded-For` is trusted only when `TRUSTED_PROXY_COUNT` is set, and then only the entry the trusted proxies appended (the Nth from the right); anything further left is client-controlled and ignored. Set it correctly in production or throttling and audit see the proxy's address.
- Every request has a correlation ID: an incoming `X-Request-ID` is kept only if it is 8-64 characters of `[A-Za-z0-9._:-]`, otherwise replaced (never echoed). It is returned in the `X-Request-ID` header (exposed to browsers by CORS), included in every error body (`request_id`) and structured log line, and stored on every audit row. Unhandled exceptions return a generic 500 with the ID and no internals; the traceback goes only to the server log.

## Audit trail (`modules/audit`, ADR-034)
Rows in `audit_events`: actor, action, outcome (`success`/`failure`/`denied`), target, workspace, request ID, client address, user agent, scrubbed `details`. Recorded inside the same transaction as the change (no change without a record, no record for a rolled-back change).

Recorded actions: `auth.register`, `auth.login.success|failure|locked`, `auth.logout`, `auth.refresh.reuse_detected`, `user.update`, `workspace.create|update`, `member.add|role_change|remove`, `location.create`, `species.create`, `asset.create|update|archive`, `observation.create`, `issue.create|update|transition|evidence_add`, `task.create|update|transition`, `agent.run`, `recommendation.accept|dismiss`, `evidence.upload|delete`, `access.denied` (HTTP 403, see below), `audit.purge` (the retention job).

Controls: append-only in PostgreSQL (trigger rejects UPDATE/DELETE from any statement, including hand-typed SQL) and in the ORM; no API creates, changes or deletes a record; the only API is `GET /workspaces/{ws}/audit`, restricted to managers and owners and scoped to the workspace (RLS also enabled). `details` is scrubbed (credential-like keys dropped, strings truncated, payload size-capped), call sites pass allow-listed fields only (profile and workspace updates record field *names*, not values), failed logins keep only a 16-character email hash. Attempts rejected while locked are deliberately not recorded (an attacker could otherwise flood the table); the lock itself is.

### Authorization denials (`modules/audit/denied.py`, ADR-036)
Every 403, whether raised by the role dependencies or deep in a service, passes through one exception handler that records an `access.denied` event (outcome `denied`) and then answers exactly as before. Recorded: actor and workspace (when authentication had resolved them), request ID, client address, HTTP method, the route **template** (`/api/v1/workspaces/{ws}/assets`, never ids or query strings), the reason code and its message. Never recorded: request bodies, headers, tokens, query strings. Best-effort and bounded: a failure to record is logged and never changes the response; a re-entrancy guard prevents recursion; identical events (same actor, route, reason) are recorded at most once per `AUDIT_DENIED_DEDUPE_S` (60 s) per process. Not recorded as denials: 401 (unauthenticated noise) and 404 for a non-member (existence is hidden by design). Managers see denials in the audit log.

### Audit retention (`modules/audit/retention.py`, ADR-035)
`AUDIT_RETENTION_DAYS` (default 730; 0 keeps everything; otherwise at least 30). The housekeeping job (`python -m app.tools.housekeeping [--dry-run]`) deletes records older than the period in batches and records an `audit.purge` event. Three independent layers refuse a bad purge: the setting validator, the purge function, and the PostgreSQL trigger `gg_audit_guard`, which allows a DELETE only inside a transaction that set `gg.audit_purge = on` **and** only for rows older than 30 days (a floor enforced by the database whatever the application does). UPDATE is never allowed. This protects against bugs and mistakes, not against a database administrator, who can change the trigger. Backups keep older records until they are pruned (BACKUP_RECOVERY.md).

## Background worker (`app/worker.py`, ADR-039)
The worker is the system acting without a user, so it is the one process that reads every workspace; inside a run every query is filtered by that run's `workspace_id`, and tests prove a scheduled run neither reads nor writes another tenant's recommendations. It creates no issues, tasks or notifications by itself: it only writes recommendations that a manager must accept. It runs as the same non-root user as the API, holds the same environment secrets and needs no inbound port. Failure reasons in the run history are truncated and pass through a redaction of `password|secret|token|key|authorization = value` patterns (a test injects a secret into an exception message and asserts it never reaches the history or the response); stack traces stay in logs. A worker cannot be tricked into overlapping runs by repeated manual triggers (409). The weather request carries only rounded coordinates of assets with open watering work (cells of ~11 km), never user or workspace identifiers.

## Dataset catalog and label review (`modules/datasets`, ADR-044)
Evidence URLs and source URLs are stored as text and never fetched by the server, so there is no server-side request surface and nothing is downloaded. Evidence, approval history, label reviews and splits are append-only in the database; approving or rejecting a dataset is limited to owners and admins (a manager's attempt is a recorded 403); the reviewer of a label is always the authenticated user (the request has no field for a name, and an extra field is rejected); a self-declared qualification is stored but marked unverified. Samples and splits cannot reference another workspace's dataset (composite foreign keys, tested on PostgreSQL); all 17 routes are in the tenancy matrix. Actions are audited (`dataset.create`, `dataset.evidence`, `dataset.status`, `dataset.samples`, `label.review`, `dataset.split`).

## Containers and delivery
Images run as non-root (API uid 10001, web uid 101), hold no secrets (all configuration arrives as environment variables), have health checks, are built in multi-stage builds, and the web image applies pending OS security upgrades at build. The API image refuses to start without a signing secret. CI lints the Dockerfiles (hadolint), scans both images with Trivy (fails on fixable HIGH/CRITICAL vulnerabilities) and audits Python and Node production dependencies (`pip-audit`, `npm audit`). The web tier sends a Content-Security-Policy, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and `Permissions-Policy`; the CSP allows only the app itself, `blob:`/`data:` images and the OpenStreetMap tile hosts. Third-party GitHub Actions are pinned by tag, not by commit SHA (a possible further hardening). See DEPLOYMENT.md.

## Tenant isolation and database permissions
Every workspace route resolves the workspace through `workspace_ctx` (non-members get 404, never 403), queries are filtered by workspace, cross-table links use composite `(workspace_id, id)` foreign keys, and RLS is enabled deny-by-default on every table (a test fails if a table is missed). A test lists every `{ws}` route and proves isolation for each; a route cannot ship unlisted.

## Evidence uploads
Type decided from the bytes (JPEG, PNG, WebP), size and decoded-pixel caps, full decode to reject corrupt files, server-generated storage keys, authenticated retrieval, soft delete (ADR-031). EXIF is retained, so GPS tags are visible to workspace members.

## Secrets
Environment only (`backend/.env`, gitignored); `.env.example` lists names. Never place secrets in `details`, logs or commits. CI uses a throwaway database and no real credentials.

## Open items
Run history and recommendations are not yet pruned (they grow slowly: one run per workspace per day); a retention policy for `agent_runs` is a follow-up. Pin GitHub Actions by commit SHA; a runtime vulnerability scan of deployed images on a schedule (CI scans at build time only); Email verification and password reset; refresh token in `sessionStorage` (planned: httpOnly cookie); recording of 403 "access denied" events; audit log retention/export and a read UI; antivirus scanning of uploads; dependency vulnerability scanning in CI; a formal security review before production.
