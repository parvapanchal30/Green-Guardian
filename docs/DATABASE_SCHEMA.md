# Database Schema (PostgreSQL 16 + PostGIS) — design

Conventions: `id uuid` (UUIDv7) PK; `workspace_id uuid NOT NULL REFERENCES workspace` on every tenant table; `created_at/updated_at timestamptz`; enums as `text` + CHECK (easier migrations than PG enums); geometry SRID 4326; all FKs indexed; composite indexes lead with `workspace_id`. Managed by Alembic. *This is the design; the migration files are the implementation truth once they exist.*

## Identity & tenancy
- `user(id, email citext unique, password_hash, name, phone, is_active, last_login_at)`
- `organization(id, name, slug unique)`
- `membership(id, organization_id, workspace_id nullable, user_id, role CHECK in (owner,admin,manager,worker,viewer))` — unique `(user_id, workspace_id)`; org-level rows have null workspace.
- `workspace(id, organization_id, name, mode CHECK in (green_management,agricultural_production), timezone, settings jsonb, capabilities jsonb, key_counters jsonb)`
- `refresh_token(id, user_id, token_hash, expires_at, revoked_at)`
- `project(id, workspace_id, name, mode, start_date, end_date, status)`

## Spatial structure
- `location(id, workspace_id, project_id, parent_id, kind CHECK in (site,field,zone,plot), name, boundary geometry(MultiPolygon,4326), centroid geometry(Point,4326), area_m2, attributes jsonb /*soil_type, ph, irrigation*/, archived_at)`
  - GiST `(boundary)`, btree `(workspace_id, project_id, kind)`

## Catalog
- `species(id, workspace_id nullable /*null = global seed*/, category, common_name, scientific_name, lifecycle_template_id, params jsonb /*stage durations, spacing, water need*/)`
- `lifecycle_template(id, workspace_id nullable, mode, name, stages jsonb /*ordered [{key,label,typical_days}]*/, transitions jsonb)`
- `workflow_template(id, workspace_id nullable, entity CHECK in (issue,task), key, states jsonb, transitions jsonb)`

## Assets
- `planting(id, workspace_id, project_id, location_id, species_id, planted_at, planned_area_m2, source, notes)`
- `biological_asset(id, workspace_id, project_id, location_id, planting_id, parent_asset_id, species_id, kind, tracking_mode CHECK in (individual,population), label, tag_code, estimated_count, position geometry(Point,4326), planted_at, current_stage, attributes jsonb, archived_at)`
  - unique `(workspace_id, tag_code)` where not null; GiST `(position)`; btree `(workspace_id, project_id, location_id, kind)`
- `lifecycle_event(id, workspace_id, asset_id, stage, entered_at, source, actor_id, note)` — append-only; idx `(asset_id, entered_at desc)`
- `asset_state` **(projection, rebuildable)** `(asset_id PK, workspace_id, current_stage, health_score, health_band, health_observed_at, growth_percent, growth_observed_at, last_observed_at, open_issue_count, open_task_count, flags jsonb, updated_at)` — idx `(workspace_id, health_band)`, `(workspace_id, last_observed_at)`

## Observations (append-only)
- `observation(id, workspace_id, asset_id nullable, location_id nullable, observed_at, observer_id nullable, source CHECK in (human,model,sensor,import,agent), method text, kind CHECK in (inspection,health,growth,symptom,environment,harvest,other), symptoms text[], notes, data jsonb, supersedes_id, task_id nullable, issue_id nullable)` — CHECK `asset_id OR location_id`; idx `(workspace_id, asset_id, observed_at desc)`, GIN `(symptoms)`
- `health_record(id, workspace_id, asset_id, observation_id, observed_at, score numeric(5,2) CHECK 0..100, category, confidence nullable, source, method)` — idx `(asset_id, observed_at desc)`
- `growth_record(id, workspace_id, asset_id, observation_id, observed_at, percent numeric(5,2), metrics jsonb /*height_cm, girth_cm, canopy_m2, flowering_pct, fruit_set_pct*/, source, method)`
- `environment_reading(id, workspace_id, location_id, observed_at, kind /*soil_moisture, temp, rainfall, ...*/, value numeric, unit, source)` — candidate for time partitioning
- `weather_record(id, workspace_id, location_id, ts, kind /*observed|forecast*/, data jsonb, provider)`
- `attachment(id, workspace_id, owner_type, owner_id, storage_key, mime, bytes, sha256, width, height, exif_gps geometry nullable, uploaded_by)`

## Issues
- `issue(id, workspace_id, key text /*GG-001*/, project_id, title, description, category, severity, state, workflow_template_id, subject_type, subject_id, location_id, assignee_id, source CHECK in (manual,observation,agent,model), recommendation_id, resolution jsonb, opened_at, resolved_at, version int)` — unique `(workspace_id, key)`; idx `(workspace_id, state, severity)`, `(workspace_id, assignee_id, state)`
- `issue_asset(issue_id, asset_id)` — cluster membership
- `issue_evidence(issue_id, observation_id | attachment_id)`
- `issue_status_history(id, workspace_id, issue_id, from_state, to_state, actor_id, note, at)` — append-only

## Tasks & operations
- `task(id, workspace_id, key, project_id, type, title, description, subject_type, subject_id, location_id, issue_id, assignee_id, priority CHECK p1..p4, status, due_at, started_at, completed_at, source CHECK in (manual,issue,agent,schedule), recommendation_id, recurrence_id, cost numeric nullable, completion_notes, version int)` — idx `(workspace_id, assignee_id, status, due_at)`, `(workspace_id, issue_id)`
- `task_status_history(id, workspace_id, task_id, from_status, to_status, actor_id, note, at)`
- `recurrence_rule(id, workspace_id, template jsonb, rrule text, scope jsonb, next_run_at, active)`
- `treatment(id, workspace_id, issue_id, task_id, asset_id|location_id, product, dose, method, applied_at, applied_by, cost)`
- `harvest(id, workspace_id, asset_id /*batch*/, task_id, harvested_at, quantity numeric, unit, grade, revenue numeric nullable, notes)`

## Intelligence
- `recommendation(id, workspace_id, rule_key, method CHECK in (rule,statistical,model,llm), subject_type, subject_id, dedupe_key, title, explanation, evidence jsonb, proposed_action jsonb /*{create:'task',...}*/, severity, status, accepted_entity_type, accepted_entity_id, dismissed_reason, expires_at, created_by_run_id)` — partial unique `(workspace_id, dedupe_key) WHERE status='open'`
- `prediction(id, workspace_id, subject_type, subject_id, kind, model_key, model_version, made_at, horizon, value jsonb, lower, upper, confidence, inputs jsonb)` — **reserved; unused in MVP**
- `job(id, type, payload jsonb, run_at, status, attempts, locked_by, locked_at, last_error)`; `job_run(id, job_id, workspace_id, started_at, finished_at, status, stats jsonb)`
- `rule_config(id, workspace_id, rule_key, enabled, params jsonb)`

## Reporting
- `report(id, workspace_id, template_key, params jsonb, status, storage_key, generated_at, requested_by)`

## Integrity & performance notes
- Cross-tenant FK safety: composite FKs `(workspace_id, id)` on high-risk links (asset→location, task→issue) or service-level checks + tests.
- N+1 avoidance: list endpoints join `asset_state`; use `selectinload` deliberately; no per-row queries in serializers.
- Partitioning candidates (by `observed_at` month) when volumes demand: `observation`, `health_record`, `environment_reading`.
- Map query: `WHERE workspace_id=$1 AND position && ST_MakeEnvelope(...)` + server-side clustering at low zoom (`ST_SnapToGrid`).
- Keyset pagination on `(created_at, id)`.
- Retention: attachments referenced by history are never auto-deleted.

## Implemented schema (migrations 0001–0006) — what actually exists

Source of truth is the migration files and `alembic check` (clean against the live PostgreSQL schema). This section lists decisions that differ from, or refine, the design above.

**Tables (17, schema `greenguardian`):** `users, organizations, workspaces, memberships, refresh_tokens` (0001) · `locations, species, biological_assets, asset_states, observations, recommendations, issues, issue_observations, issue_status_history, tasks, task_status_history` (0003) · `alembic_version`. All have RLS enabled (0002 / 0003).

**Differences from the design, and why**
- **Deferred (no consumer yet):** `project`, `planting`, `parent_asset_id`, `lifecycle_event`, `health_record`/`growth_record`, `environment_reading`, `weather_record`, `prediction`, `job`, `attachment`. Health is carried by `observations.health_score` and projected into `asset_states`; photo evidence is **metadata only** (`observations.attachments` JSON) until the storage slice. `biological_assets.current_stage` is read-only until lifecycle events exist.
- **Coordinates:** `latitude`/`longitude` (portable `FLOAT`, range CHECKs, pair CHECK) are the source of truth. On PostgreSQL a **generated stored `centroid geometry(Point,4326)`** column with a GiST index is derived from them (`locations`, `biological_assets`). The ORM does not map it (`include_object` in `migrations/env.py` ignores exactly those columns/indexes); spatial queries use it directly. Verified: `POINT(lon lat)`, bbox `&&` queries, update propagation.
- **Tenant integrity in the database:** every tenant table has `UNIQUE (workspace_id, id)` and cross-table links are **composite foreign keys** `(workspace_id, x_id)`, so a service bug cannot link records across workspaces (tested with direct SQL).
- **Append-only history:** `BEFORE UPDATE OR DELETE` triggers (`gg_forbid_mutation()`, pinned `search_path`, not executable by PUBLIC) on `observations`, `issue_status_history`, `task_status_history`. Consequence: users with history cannot be deleted (FKs are `RESTRICT`); erasure means anonymising the user row.
- **Issues:** `resolved_at` is set on entering *any* terminal state; `resolution_outcome` distinguishes fixed/mitigated/no-action/duplicate/won't-fix; `CHECK ((resolved_at IS NULL) = (resolution_outcome IS NULL))`. `state` is validated against a workflow defined in code (`app/modules/issues/workflows.py`), not by a DB CHECK, so new workflows need no migration. Field edits are audited as history rows with `from_state = to_state`.
- **Keys:** `GG-001` / `T-001` allocated from `workspaces.key_counters` under `SELECT … FOR UPDATE`.
- **Recommendations:** partial unique index `uq_recommendations_open_dedupe (workspace_id, dedupe_key) WHERE status = 'open'`; dismissals are suppressed for `dismiss_suppress_days` (default 7) by the runner.
- **Seed data:** 11 global species (`workspace_id IS NULL`) inserted by `0003`.
- **Indexes:** the ones the queries use are present (see `test_indexes_exist_for_the_real_query_patterns`); the advisor's "unindexed foreign key" INFO notices are accepted for now (see DATABASE_SETUP section 9).

**`evidence` (0004, 2026-10-17):** one row per stored image. Columns: `workspace_id, asset_id` (composite FK, RESTRICT), optional `observation_id` and `issue_id` (composite FKs), `uploaded_by`, `storage_key` (unique, server-generated `{workspace}/{asset}/{id}.{ext}`), `original_filename` (display only), `content_type` (CHECK: jpeg/png/webp), `size_bytes`, `sha256`, `width`, `height`, `caption`, `created_at`, `deleted_at`/`deleted_by` (soft delete). RLS enabled. The bytes are not in the database; they live in the object store behind `ObjectStore`. The older `observations.attachments` JSON column (metadata references) is retained for compatibility and is no longer written by the UI.

**`auth_throttle` (0005):** brute-force counters. `key` (PK; hashed email or address based, never a plaintext email), `failures`, `window_started_at`, `locked_until`, `updated_at`. Global (not tenant-scoped), RLS enabled.

**Dataset tables (0008, 0009):** `datasets` (unique workspace+name+version; licence of dataset, images and annotations; `image_origin`; commercial use, redistribution, attribution; status `proposed`/`under_review`/`approved`/`rejected`; CHECK that an approved real dataset has `approved_by`), `dataset_evidence` and `dataset_status_history` (append-only), `dataset_samples` (unique dataset+external id; group key, label, `label_status`, SHA-256, 64-bit perceptual hash, file status, provenance), `label_reviews` (append-only; reviewer RESTRICT) and `dataset_splits` (append-only; unique dataset+version; manifest, checksum, stats, leakage violations). Composite `(workspace_id, dataset_id)` foreign keys; RLS enabled on all six.

**Evaluation-protocol tables (0010):** `evaluation_protocols` (append-only versions: unique workspace+key+version, JSON content, content checksum) and `protocol_signoffs` (append-only; role and decision CHECKs; `qualification_verified` locked false by CHECK `qualification_unverifiable`; signer RESTRICT; composite FK to the protocol). RLS enabled on both.

**`audit_events` (0005):** the append-only audit trail. `occurred_at`, nullable `workspace_id` and `actor_id` (foreign keys with RESTRICT: workspaces are archived and users anonymised, never deleted), `action`, `outcome` (CHECK success/failure/denied), `target_type`/`target_id`, `request_id`, `client_ip`, `user_agent`, `details` (JSONB, scrubbed). A `BEFORE UPDATE OR DELETE` trigger (`trg_audit_events_append_only`, the shared `gg_forbid_mutation()` function) rejects any change; indexes on workspace+time, actor+time, action+time, target and request ID. RLS enabled. TRUNCATE is not blocked by a row trigger; restrict it through database role privileges in production.

**Migration 0006 (audit retention guard):** replaces the audit table's trigger function with `gg_audit_guard()`. UPDATE is always rejected; DELETE is allowed only when the transaction set `gg.audit_purge = on` and the row is older than 30 days. No table changes. Downgrade restores the original `gg_forbid_mutation()` trigger.
