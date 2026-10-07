# Database Setup (hosted PostgreSQL + PostGIS)

Decision: development uses a **hosted PostgreSQL database with PostGIS**, Supabase by default (ADR-015). The application treats it as plain PostgreSQL+PostGIS: all access goes through the backend (SQLAlchemy/Alembic); no Supabase client libraries, Auth, Storage, RLS or Data API are used. Moving to another managed provider (Neon, RDS, Cloud SQL, Azure, Crunchy, self-hosted) means changing environment variables only.

_Provider facts below were checked against Supabase's and Open-Meteo's official docs on 2026-10-06; re-verify if a provisioning step fails — providers change._

## 1. Requirements the app imposes

| Requirement | Value | Why |
|---|---|---|
| PostgreSQL | **15 or newer** (developed against 15–17) | `gen_random_uuid()`, `jsonb`, partial indexes, `SKIP LOCKED` jobs. UUIDv7 is generated **client-side**, so PG18's native `uuidv7()` is not required. |
| PostGIS | **3.x**, installed with `CREATE EXTENSION postgis` | Geometry/geography columns, GiST indexes, `ST_*`, bbox `&&` (map, locations, assets). |
| Extension install schema | A **dedicated schema**, default `extensions` (env `POSTGIS_SCHEMA`) — never `public` | Supabase warns `spatial_ref_sys` becomes exposed through its Data API if PostGIS lives in `public`. PostGIS ≥ 2.3 is non-relocatable (moving it = drop + recreate). |
| `search_path` | Must include the PostGIS schema, e.g. `public, extensions` | So unqualified `geometry`/`ST_*` resolve. The app sets this on every new connection (SQLAlchemy `connect` event) rather than via startup options, because poolers may reject startup parameters. |
| TLS | `sslmode=require` | Provider docs: default may fall back to plaintext. |
| Role | A role that owns the app schema and can run migrations (`CREATE TABLE`, `CREATE EXTENSION` on first run) | Alembic runs as the same role in dev. In prod use a migration role and a restricted runtime role (V2 hardening). |
| Not used | Supabase Auth/Storage/Realtime/RLS/PostgREST | Keeps portability; tenant isolation is enforced in the service layer (+ tests), see ARCHITECTURE §3. |

## 2. Connection modes (Supabase, free tier)

| Mode | URL shape | Network | Use for |
|---|---|---|---|
| Direct | `postgresql://postgres:<pw>@db.<ref>.supabase.co:5432/postgres` | **IPv6 only** unless the paid IPv4 add-on | Long-running containers on IPv6-capable hosts |
| Shared pooler — **session** | `postgresql://postgres.<ref>:<pw>@<pooler-host>:5432/postgres` | IPv4 | **Default for dev and for the containerized API/worker** (supports prepared statements, `SET`, transactions) |
| Shared pooler — transaction | same host, port **6543** | IPv4 | Serverless/edge only. **No prepared statements; session state not preserved.** |

App support:
- `DATABASE_URL` takes the SQLAlchemy form `postgresql+psycopg://…` (driver: psycopg 3). Plain `postgresql://` URLs from provider dashboards are rewritten automatically.
- `DB_POOL_MODE=session` (default): normal SQLAlchemy `QueuePool` (size/overflow from env).
- `DB_POOL_MODE=transaction`: `NullPool` + `prepare_threshold=None` (disables server-side prepared statements) — required if you must use port 6543.
- Many dev machines/networks lack IPv6: if direct connect times out, use the **session pooler** string.

## 3. One-time setup (done by a human in the Supabase dashboard)

Creating a Supabase project needs your account and generates credentials, so it is deliberately **not** automated by the repo or by Claude.

1. Create a project (any region near you). Note the database password.
2. Dashboard → **Database → Extensions**: enable **postgis** and choose/create the schema **`extensions`** (equivalent SQL: `create extension if not exists postgis with schema extensions;`). The first Alembic migration also runs this idempotently.
3. Dashboard → **Connect**: copy the **Session pooler** connection string.
4. Locally: `cp backend/.env.example backend/.env` and set `DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@<pooler-host>:5432/postgres?sslmode=require`. `.env` is gitignored. **Never commit credentials**; share them through the team's secret channel.
5. Set `TEST_DATABASE_URL`. **Recommended value: the same string as `DATABASE_URL`** (see section 5 for why that is safe). The old advice below still applies if you prefer a separate database.
   (Original note:) Set `TEST_DATABASE_URL`. Prefer a **second, disposable** database/project. It may also equal `DATABASE_URL`: the PostGIS tests run only inside a uniquely named throwaway schema (`gg_test_<random>`) that is dropped afterwards, they never touch `public`, and PostGIS itself is installed once (idempotent).
6. Apply the schema: `cd backend && .venv/Scripts/python -m alembic upgrade head`.
7. Verify: `.venv/Scripts/python -m app.tools.check_db` (prints server version, PostGIS version, schema, search_path; exits non-zero if requirements aren't met).

## 4. Migration & portability rules

- Alembic is the only way schema changes happen. No Supabase-specific SQL in migrations (no `auth.*`, `storage.*`, no RLS policies, no `supabase_*` roles).
- The PostGIS migration step reads `POSTGIS_SCHEMA`; on a provider that puts PostGIS in `public` set `POSTGIS_SCHEMA=public`.
- `GG_REQUIRE_POSTGIS=false` lets migrations run on a database *without* PostGIS (used only by tests of non-spatial code). Spatial migrations (locations/assets) will refuse to run without PostGIS.
- Dialect-neutral types are used for non-spatial tables (`Uuid`, `JSON` with a `JSONB` variant on PostgreSQL), so fast unit tests can run on in-memory SQLite. SQLite is **tests-only**, never a runtime target (ADR-007 amended).

## 5. Test strategy for the database

| Layer | Runs on | When |
|---|---|---|
| Rules, workflow, health bands, weather mapping | none / in-memory | every run |
| Repositories, auth, tenant isolation, RBAC (non-spatial) | in-memory SQLite | every run |
| Alembic ↔ models drift check | SQLite (non-PG parts) | every run |
| Spatial queries, PostGIS migrations, PG-specific behaviour | real PostgreSQL+PostGIS via `TEST_DATABASE_URL` | when set; **required in CI** (service container `postgis/postgis`) |

**Why `TEST_DATABASE_URL` may equal `DATABASE_URL`:** the non-PostGIS tests never connect to it (they build SQLite settings with `_env_file=None`); the PostGIS tests (a) only act inside a generated schema `gg_test_<8 hex>` (name validated before every DDL), (b) connect with `search_path = <that schema>, extensions` so unqualified names cannot resolve to `public` or `greenguardian`, (c) snapshot every table outside the test schema before and after and fail on any difference, and (d) always `DROP SCHEMA ... CASCADE` only that generated schema. Residual risk: a future test that bypasses the fixture; keep new database tests on the `pg_schema` fixture.

Tests marked `@pytest.mark.postgis` are skipped (with a visible reason) when `TEST_DATABASE_URL` is unset — a skipped run is **not** a verified run for spatial code.

## 6. Production notes
Use managed PostgreSQL+PostGIS with PITR backups; run API/worker containers on a network with a supported connection mode (session pooler or direct); separate migration and runtime roles; set pool sizes so `instances × (pool_size + max_overflow)` stays below the provider's connection limit; monitor connection counts.

## 7. Weather provider (Open-Meteo) — constraints and licensing risk (R-WX-1)
- Endpoint `https://api.open-meteo.com/v1/forecast`; required `latitude`, `longitude`; hourly variables used: `precipitation`, `precipitation_probability`, `soil_moisture_0_to_1cm` … `soil_moisture_27_to_81cm`, `et0_fao_evapotranspiration`, `temperature_2m`; `forecast_days` 0–16, `timezone=auto`.
- **Licensing / commercial use — a risk that must be verified before any commercial deployment.** As read from Open-Meteo's terms page on 2026-10-07: the free API is described as for **non-commercial** use, with stated limits of fewer than 10,000 calls/day, 5,000/hour and 600/minute; data is under CC BY 4.0 (attribution required, and we return an attribution string with every forecast); the terms list "integration into commercial products" among commercial uses, and describe paid subscription tiers that remove the limits and allow commercial use. The terms page does not give the paid endpoint/key mechanics, so none is implemented. Terms and pricing change: **re-read them and obtain a licence (or switch provider) before charging for, or running ads on, anything that calls this API.** Nothing here is legal advice.
- Mitigation by design: weather is reached only through `WeatherContextProvider` (agent-owned port) → `WeatherService` → `WeatherProvider` → a registered adapter (ADR-024). Replacing Open-Meteo means one new adapter and one environment value; no agent, domain or API code changes. Tests never call the live API.
- Forecasts are fetched on demand and cached in-process (TTL); persisted `weather_record` rows are a later step.

## 8. Troubleshooting (all seen in practice)

| Symptom | Cause | Fix |
|---|---|---|
| `password authentication failed for user "postgres"` although the password is right | The dashboard string is `postgres:[YOUR-PASSWORD]@...`; the `[ ]` are a **placeholder marker**, not part of the password. Keeping them makes the password wrong. | Remove the brackets. `Settings` now rejects a bracket-wrapped password with a clear message. Passwords containing `@ : / ? # %` must be URL-encoded. |
| `check_db` reports `IPv4=no-address, IPv6=timeout` / connection timeout | Supabase's **direct** host (`db.<ref>.supabase.co`) is IPv6-only on the free tier, and this network has no working route to it (IPv6 can work intermittently on home/campus networks). | Use the **Session pooler** string (Dashboard → Connect → Session pooler: user `postgres.<ref>`, host `aws-*-<region>.pooler.supabase.com`, port 5432). It is IPv4. |
| Commands hang | Older code had no connect timeout. | `DB_CONNECT_TIMEOUT_S` (default 10) now bounds every connection attempt; `check_db` probes TCP reachability first. |
| `TEST_DATABASE_URL not set` skips | Variable empty/missing in `backend/.env` | Set it (see step 5). A run with skipped PostGIS tests has **not** verified PostgreSQL behaviour. |

## 9. Verified state of the development database (2026-10-07, project `greenguardian`, ap-northeast-2)

Checked through the Supabase connector and the app's own tooling:

| Item | Result |
|---|---|
| Server | PostgreSQL 17.11 |
| PostGIS | 3.3.7, installed in schema `extensions` (not `public`); `spatial_ref_sys` has 8,500 rows there |
| Connection | Session pooler (IPv4), TLS in use on the client connection, `search_path = greenguardian, extensions` |
| Application schema | `greenguardian` with `users, organizations, workspaces, memberships, refresh_tokens, alembic_version`; Alembic head `0001` |
| `public` | empty (0 tables) by design |
| Supabase-managed schemas | `auth, storage, realtime, vault, ...` untouched |
| Test run | `pytest` 73 passed, 0 skipped (6 PostGIS tests executed); afterwards 0 leftover `gg_test_*` schemas and `public` unchanged |

### Why application tables are NOT in `public` (ADR-022)
On Supabase, `public` is exposed through the Data API and receives default grants for `anon`/`authenticated`. With RLS off, `users` (password hashes) would be readable with the public anon key. The app therefore uses its own schema (`DB_SCHEMA`, default `greenguardian`), which Supabase does not expose. Verified: `anon` and `authenticated` have no `USAGE` on `greenguardian` and no `SELECT` on `greenguardian.users`; the project security advisor reports no lints.

### Row Level Security: final model (migration `0002`, ADR-023)
RLS is **enabled on every application table** (17 of 17, including `alembic_version`) with **no policies**: deny-by-default for every role that neither owns the tables nor has `BYPASSRLS`.

| Role | Relationship | Effect |
|---|---|---|
| `postgres` (the role the backend connects as) | owns all tables; `rolbypassrls = true` (verified) | unaffected by RLS: the app works exactly as before |
| `anon`, `authenticated` | no privilege on the schema or any table (`REVOKE ALL` + default privileges revoked); not API-exposed | cannot read or write anything, and RLS would hide every row even if a grant were ever added |
| any future non-owner runtime role without `BYPASSRLS` | n/a | sees **zero rows** until explicit policies are added in a migration (intentional fail-closed behaviour) |

Rules: (1) tenancy is enforced by the service layer; RLS is the second barrier, not the first. (2) We do **not** use `FORCE ROW LEVEL SECURITY`. (3) Every migration that creates a table must call `app.core.rls.enable_rls("<table>")`; `test_every_application_table_has_rls_enabled_and_no_policies` fails otherwise. (4) `check_db` reports the RLS count and whether the connected role owns the tables or bypasses RLS, and fails if neither.

Verified through Supabase after applying `0002` and `0003`: RLS on all tables, 0 policies, 0 grants to `anon`/`authenticated`, no schema `USAGE` for `anon`, the `gg_forbid_mutation()` trigger function not executable by them. The security advisor reports only the **INFO** notice `rls_enabled_no_policy` on all 17 tables, which is the intended state (the earlier *critical* "RLS disabled" finding is gone). A test also proves the barrier works: a throwaway role granted `SELECT` sees 0 rows while the owner sees the row.

### Performance advisor notes (accepted for now)
The Supabase performance advisor reports INFO items only: 26 "foreign keys without a covering index" and 27 "unused indexes". The unused-index notice is expected on an empty development database. The unindexed foreign keys are mostly composite `(workspace_id, x_id)` tenant-integrity keys and user references (`created_by`, `actor_id`, ...) on tables we never delete from; the hot query paths (by workspace + asset/issue/task/assignee/status) already have indexes. Adding 26 speculative indexes would slow every write, so they are deliberately **not** added now; revisit with real query statistics (`pg_stat_statements`) before production.

### Troubleshooting additions
| Symptom | Cause | Fix |
|---|---|---|
| `check_db` once showed `TLS = False` | `pg_stat_ssl` reports the *pooler→database* hop for pooled connections | The check now reads the client connection (`pgconn.ssl_in_use`) |
| `DATABASE_URL` database name looks like `postgres# session (default) ...` | A template comment line was joined onto the URL line; python-dotenv only treats ` #` (with a space) as a comment | Keep `DATABASE_URL=...` on its own line |
| PostGIS tests skip although `.env` has `TEST_DATABASE_URL` | `os.getenv` does not read `.env` | Fixed: `tests/conftest.py` falls back to `backend/.env` |
