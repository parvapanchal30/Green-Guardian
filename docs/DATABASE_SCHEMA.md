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
