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
5. Set `TEST_DATABASE_URL`. Prefer a **second, disposable** database/project. It may also equal `DATABASE_URL`: the PostGIS tests run only inside a uniquely named throwaway schema (`gg_test_<random>`) that is dropped afterwards, they never touch `public`, and PostGIS itself is installed once (idempotent).
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

Tests marked `@pytest.mark.postgis` are skipped (with a visible reason) when `TEST_DATABASE_URL` is unset — a skipped run is **not** a verified run for spatial code.

## 6. Production notes
Use managed PostgreSQL+PostGIS with PITR backups; run API/worker containers on a network with a supported connection mode (session pooler or direct); separate migration and runtime roles; set pool sizes so `instances × (pool_size + max_overflow)` stays below the provider's connection limit; monitor connection counts.

## 7. Weather provider (Open-Meteo) — constraints that affect the database/config
- Endpoint `https://api.open-meteo.com/v1/forecast`; required `latitude`, `longitude`; hourly variables used: `precipitation`, `precipitation_probability`, `soil_moisture_0_to_1cm`…`soil_moisture_27_to_81cm`, `et0_fao_evapotranspiration`, `temperature_2m`; `forecast_days` 0–16, `past_days` 0–92, `timezone=auto|IANA`.
- **The free API is for non-commercial use only.** A commercial deployment needs an API key + customer endpoint. This is recorded as risk R-WX-1; the provider is behind an interface so it can be swapped (see ARCHITECTURE §5/AI_ARCHITECTURE `WeatherProvider`).
- Forecasts are fetched on demand and cached in-process (TTL); persisted `weather_record` rows are a later step.

## 8. Troubleshooting (all seen in practice)

| Symptom | Cause | Fix |
|---|---|---|
| `password authentication failed for user "postgres"` although the password is right | The dashboard string is `postgres:[YOUR-PASSWORD]@...`; the `[ ]` are a **placeholder marker**, not part of the password. Keeping them makes the password wrong. | Remove the brackets. `Settings` now rejects a bracket-wrapped password with a clear message. Passwords containing `@ : / ? # %` must be URL-encoded. |
| `check_db` reports `IPv4=no-address, IPv6=timeout` / connection timeout | Supabase's **direct** host (`db.<ref>.supabase.co`) is IPv6-only on the free tier, and this network has no working route to it (IPv6 can work intermittently on home/campus networks). | Use the **Session pooler** string (Dashboard → Connect → Session pooler: user `postgres.<ref>`, host `aws-*-<region>.pooler.supabase.com`, port 5432). It is IPv4. |
| Commands hang | Older code had no connect timeout. | `DB_CONNECT_TIMEOUT_S` (default 10) now bounds every connection attempt; `check_db` probes TCP reachability first. |
| `TEST_DATABASE_URL not set` skips | Variable empty/missing in `backend/.env` | Set it (see step 5). A run with skipped PostGIS tests has **not** verified PostgreSQL behaviour. |
