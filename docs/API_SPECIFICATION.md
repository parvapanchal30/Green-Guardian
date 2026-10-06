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
POST  /workspaces/{ws}/agent/run               admin: trigger sweep now
GET   /workspaces/{ws}/agent/runs              run history
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

## Implementation status (2026-10-07)
Implemented and tested: `POST /auth/register|login|refresh|logout`, `GET|PATCH /me`, `GET|POST /workspaces`, `GET|PATCH /workspaces/{ws}`, `GET /workspaces/{ws}/capabilities`, members `GET|POST /workspaces/{ws}/members`, `PATCH|DELETE /workspaces/{ws}/members/{user_id}`, `GET /workspaces/{ws}/weather`, `GET /healthz`, `GET /readyz`. Everything else in this document is still design.
