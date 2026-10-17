# API Specification (v1 design)

Base: `/api/v1`. JSON. Auth: `Authorization: Bearer <access JWT>`. Workspace-scoped resources live under `/workspaces/{ws}/…` (the `{ws}` is validated against the caller's membership on every request). Errors: RFC 7807 `application/problem+json` with `code`, `detail`, `errors[]` for validation. Pagination: `?limit=50&cursor=…` → `{items, next_cursor}`. Filters via query params. Mutable aggregates (issue, task) carry `version`; `PATCH` requires `If-Match: <version>` (409 on mismatch). OpenAPI is generated and is the contract of record once code exists; this file records intent.

## Auth & identity
```
POST /auth/register            POST /auth/login          POST /auth/refresh      POST /auth/logout
GET  /me                       PATCH /me
GET  /workspaces               POST /workspaces                     {name, mode}
GET  /workspaces/{ws}          PATCH /workspaces/{ws}               settings, thresholds, capabilities(read-only)
GET/POST/PATCH/DELETE /workspaces/{ws}/members
```

## Structure
```
GET/POST        /workspaces/{ws}/projects            GET/PATCH /projects/{id}
GET/POST        /workspaces/{ws}/locations           ?kind=&parent_id=&project_id=
GET/PATCH/DELETE(archive) /workspaces/{ws}/locations/{id}
GET             /workspaces/{ws}/species             POST (custom)       GET /species/{id}
GET             /workspaces/{ws}/lifecycle-templates
```

## Assets
```
GET   /workspaces/{ws}/assets                  ?kind=&location_id=&stage=&health_band=&q=&bbox=&has_open_issue=
POST  /workspaces/{ws}/assets                  create (+ optional initial observation)
POST  /workspaces/{ws}/assets:bulk             CSV/GeoJSON import (V2)
GET   /workspaces/{ws}/assets/{id}             profile with asset_state
PATCH /workspaces/{ws}/assets/{id}
POST  /workspaces/{ws}/assets/{id}/lifecycle   {stage, entered_at, note}
GET   /workspaces/{ws}/assets/{id}/timeline    merged observations/lifecycle/issues/tasks
GET   /workspaces/{ws}/assets/{id}/health      ?from=&to=   time series
GET   /workspaces/{ws}/assets/{id}/growth      ?from=&to=
```

## Observations & evidence
```
GET   /workspaces/{ws}/observations            ?asset_id=&location_id=&kind=&from=&to=
POST  /workspaces/{ws}/observations            {asset_id|location_id, observed_at, kind, health?, growth?, symptoms[], notes, data, attachment_ids[]}
POST  /workspaces/{ws}/attachments             multipart upload → {id, url(signed)}
GET   /workspaces/{ws}/environment-readings    POST
```
Observations are immutable; correct via `POST` with `supersedes_id`.

## Issues
```
GET   /workspaces/{ws}/issues                  ?state=&severity=&category=&assignee=&asset_id=&location_id=&q=
POST  /workspaces/{ws}/issues
GET   /workspaces/{ws}/issues/{id}             includes history, evidence, tasks, assets
PATCH /workspaces/{ws}/issues/{id}             title/desc/severity/assignee (If-Match)
POST  /workspaces/{ws}/issues/{id}/transitions {to_state, note}     → validated against workflow
POST  /workspaces/{ws}/issues/{id}/evidence    {observation_id|attachment_id}
GET   /workspaces/{ws}/issues/workflows        template states/transitions for UI
```

## Tasks
```
GET   /workspaces/{ws}/tasks                   ?status=&assignee=me&due_before=&issue_id=&asset_id=&type=
POST  /workspaces/{ws}/tasks
GET/PATCH /workspaces/{ws}/tasks/{id}          (If-Match)
POST  /workspaces/{ws}/tasks/{id}/transitions  {to_status, note, observation?}  → completion can attach an observation
GET/POST /workspaces/{ws}/recurrence-rules
```

## Intelligence (MVP = rules)
```
GET   /workspaces/{ws}/recommendations         ?status=open&severity=&subject_id=
POST  /workspaces/{ws}/recommendations/{id}/accept    → creates issue/task per proposed_action; returns entity ref
POST  /workspaces/{ws}/recommendations/{id}/dismiss   {reason}
GET   /workspaces/{ws}/agent/rules             list + params;  PATCH /agent/rules/{key} enable/thresholds
POST  /workspaces/{ws}/agent/run               manager: run now (409 `agent_run_in_progress` while another run is active; response includes the recorded run)
GET   /workspaces/{ws}/agent/runs              execution history, manual and scheduled, newest first (member; paginated)
GET   /workspaces/{ws}/agent/runs/{run_id}     one run: counts, rules and versions, diagnostics, error
GET   /workspaces/{ws}/predictions             reserved → returns [] + capability.available=false in MVP
GET   /workspaces/{ws}/capabilities            [{key,label,technique,stage:mvp|v2|v3|v4,available,reason}] — implemented
```
Future (reserved, return `501 capability_unavailable` with `Problem.code`): `POST /ai/crop-recommendations`, `POST /ai/disease-scans`, `POST /ai/irrigation-plans`.

## Read models
```
GET /workspaces/{ws}/dashboard                 ?project_id=   mode-shaped KPI payload (+ per-KPI `available`/`reason`)
GET /workspaces/{ws}/map                       ?bbox=&layers=assets,health,issues,tasks,boundaries&zoom=  → GeoJSON FeatureCollections per layer
GET /workspaces/{ws}/map/layers                registry incl. disabled/future layers
GET /workspaces/{ws}/weather                   ?lat=&lon=&days=1..16  (provider-neutral forecast + source/attribution; 503 weather_unavailable on failure). `location_id` replaces lat/lon once locations exist.
```

## Reports
```
GET /workspaces/{ws}/reports/templates     POST /workspaces/{ws}/reports     GET /reports/{id}     GET /reports/{id}/download
```

## System
`GET /healthz` · `GET /readyz` · `GET /openapi.json`

## Dashboard payload shape (illustrative)
```json
{"mode":"green_management","as_of":"2026-10-06T10:00:00Z",
 "kpis":{"trees":{"value":18420},"healthy":{"value":15982},"at_risk":{"value":1840},"critical":{"value":598},
         "survival":{"value":0.913,"basis":"alive/planted"},
         "canopy":{"available":false,"reason":"No canopy measurements recorded"},
         "open_issues":{"value":37},"open_tasks":{"value":112}},
 "attention":[{"recommendation_id":"…","title":"Tree #482 has not been inspected in 21 days","severity":"medium"}]}
```
Every KPI is either a computed value (with `basis`) or `available:false` with a reason — never a fabricated number.

## Implementation status (2026-10-07, vertical slice)

All paths are under `/api/v1/workspaces/{ws}`. Lists return `{items, total, limit, offset}` (`limit` 1–200, default 50). Errors are RFC 7807 problem+json with a stable `code`. Non-members get `404 workspace_not_found` for every route (verified by an OpenAPI-derived isolation matrix).

| Area | Endpoint | Min. role | Notes |
|---|---|---|---|
| Identity | `POST /auth/register|login|refresh|logout`, `GET|PATCH /me` | — / any | argon2id, JWT, rotating refresh tokens with reuse detection |
| Workspace | `GET|POST /workspaces`, `GET|PATCH /{ws}`, `GET /{ws}/capabilities`, members `GET|POST /members`, `PATCH|DELETE /members/{user_id}` | member / admin | PATCH `settings.agent` sets rule thresholds |
| Weather | `GET /weather?lat&lon&days` | member | provider-neutral; source + attribution returned |
| Locations | `GET /locations`, `POST /locations`, `GET /locations/{id}` | member / manager | zone/field/site/plot, optional parent |
| Species | `GET /species?category&q`, `POST /species` | member / manager | global seed + workspace-private |
| Assets | `GET /assets` (`kind, location_id, health_band, q, has_open_issue`), `POST /assets`, `GET|PATCH|DELETE /assets/{id}`, `GET /assets/{id}/timeline` | member / worker / manager | `DELETE` archives (soft); profile includes current `state` |
| Observations | `POST /observations`, `GET /observations?asset_id`, `GET /observations/{id}` | worker / member | immutable (no PUT/PATCH/DELETE); `POST` returns `{observation, recommendations}` |
| Issues | `GET /issues` (`state, is_open, severity, category, assignee, asset_id, q`), `POST /issues`, `GET /issues/workflows`, `GET|PATCH /issues/{id}`, `POST /issues/{id}/transitions`, `POST /issues/{id}/evidence` | member / worker / manager | transitions validated by the workflow; closing needs a resolution |
| Tasks | `GET /tasks` (`status, is_open, assignee=me|unassigned|id, issue_id, asset_id, type, overdue, q`), `POST /tasks`, `GET|PATCH /tasks/{id}`, `POST /tasks/{id}/transitions` | member / manager / assignee-or-manager | completing may carry a follow-up `observation` |
| Dashboard | `GET /dashboard?location_id&kind` | member | database-side aggregates (asset health bands, open issues by severity, open/overdue tasks, inspections due, open suggestions, recent activity) in a fixed number of statements; one shape for both modes, mode selects the KPI set; KPIs that cannot be computed are `available: false` with a reason |
| Map | `GET /map/layers`, `GET /map/layers/{layer}?filter&location_id&kind&bbox&limit` | member | one layer registry; only `assets` is served (GeoJSON points, filtered/clipped in the database: PostGIS `ST_Intersects` on the GiST-indexed `centroid` columns). Chip filters: all, healthy, at_risk, critical, open_issues, tasks; chip counts and `unlocated` in the response. An asset without coordinates is drawn at its location's centre (`position_source`). Planned layers (disease_hotspots, soil_moisture, irrigation, growth, canopy, survival_risk, yield) are listed with `available: false` and return `501 capability_unavailable` |
| Evidence | `POST /evidence` (multipart: `asset_id`, `file`, `caption?`, `observation_id?`, `issue_id?`), `GET /evidence?asset_id&observation_id&issue_id`, `GET /evidence/{id}`, `GET /evidence/{id}/content`, `DELETE /evidence/{id}` | worker (upload, delete own) / member (read) / manager (delete any) | JPEG, PNG, WebP up to `STORAGE_MAX_BYTES`; type decided from the bytes (415), corrupt (422), oversized (413), pixel limit (422); links must share the asset; `content` is authenticated (fetch with the bearer token); delete is soft |
| Audit | `GET /audit?action&actor_id&target_type&target_id&request_id&since&until`, `GET /audit/meta` (actions and target types present, retention policy for the filter UI) | manager / owner | read-only, newest first, workspace-scoped; `action` is a prefix (`issue.`); no endpoint creates, changes or deletes audit records |
| Agent | `GET /agent/rules`, `POST /agent/run`, `GET /agent/runs`, `GET /agent/runs/{id}`, `GET /recommendations?status&asset_id`, `POST /recommendations/{id}/accept|dismiss` | member / manager | rule-based only; accepting creates an issue/task, or (irrigation advice) moves a watering task's due date, through the normal services; recommendations expose `agent_run_id`, `rule_version`, `outcome*`; tasks expose `recommendation_id` |

**Conventions:** request bodies reject unknown fields; JSON blobs ≤ 10 KB; attachments are metadata (https URL or storage key, image types only, ≤ 10); `observed_at` may be back-dated but not future; `409` for illegal transitions (`allowed` lists the legal ones), open tasks blocking resolution (`open_tasks`), duplicates; `422` for validation and business-rule violations; `403` for role violations.
Still design only: `GET /dashboard`, `GET /map`, reports, bulk import, predictions (`501 capability_unavailable` is reserved). The Home dashboard currently composes counts from list totals.

## Cross-cutting behaviour (2026-10-17, ADR-032..034)
- **`X-Request-ID`** is returned on every response (and exposed to browsers by CORS). A well-formed incoming value (8-64 characters of `A-Za-z0-9._:-`) is kept; anything else is replaced. Every problem+json body includes `request_id`. Quote it to support: it matches the server log and the audit trail.
- **429 `too_many_attempts`** (login, refresh, register): includes `retry_after_s` in the body and a `Retry-After` header. Responses for unknown and known emails are identical. The attempt that crosses a limit still returns 401; subsequent attempts return 429 until the cooldown (default 15 minutes) passes.
- **500 `internal_error`**: generic body plus `request_id`; never contains exception text or stack traces.
