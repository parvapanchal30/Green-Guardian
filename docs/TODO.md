# TODO

Legend: `[ ]` open · `[~]` in progress · `[x]` done. Cleaned up on 2026-10-27: finished items that were still marked open
were closed, duplicates merged, and the list regrouped by when the work is due. What each finished item contains is in
`docs/CURRENT_STATE.md`; why, in `docs/DECISION_LOG.md`.

## Before the mid-stage presentation (30 October 2026)
- [ ] Run the automated tour (`tour.bat`) end to end against the redesigned pages and fix any step that no longer finds
  its target
- [ ] Restyle the issue page (gap G44): it is part of the demo story (Neem #102 crown dieback)
- [ ] Role names capitalised where shown alone (gap G3)
- [ ] The Hindi demo path without server-written English where it is seen (part of gap G1: suggestion titles, activity lines)
- [ ] Automated golden path in a browser, both modes: register → declining observations → suggestion → accept → task →
  worker completes with an observation → issue resolved with a check → dashboard and report reflect it (MVP exit criterion)
- [ ] Presentation: update the deck with progress, before/after screenshots and what is next (only with the owner's go-ahead)
- [ ] Rehearse on `demo.bat --fresh`, with `--offline` weather as the fallback

## Next (after the presentation)
- [ ] Work through the redesign gaps in `docs/REDESIGN_GAPS.md` (G1–G53), starting with joining a workspace (G47–G53)
- [ ] Growth and survival prediction, statistical baselines first, with uncertainty shown (Stage F/G; needs no external data)
- [ ] Workspace settings screen for the agent's schedule and thresholds (G36)
- [ ] Password reset and email verification; refresh-token reuse grace window or httpOnly cookie
- [ ] Draw field and zone boundaries on the map; zone areas, so Impact can report coverage
- [ ] Thumbnails for photos (G17, G25)
- [ ] Bulk import of plants (CSV)
- [ ] 100k-asset performance seed; security review
- [ ] Tours: more in-app steps (task and issue detail, the Record sheet), a first-run prompt for new workspaces, Hindi
  narration for the browser tour; keep `frontend/tour/steps.json` and `frontend/src/tour/steps.ts` aligned
- [ ] i18n: API codes instead of server-composed text (G1); native-speaker review of the Hindi catalog (G2); language and
  theme stored on the account (G8)
- [ ] Lifecycle and harvest follow-ups: species lifecycle durations (need domain input), partial batch loss (a count
  ledger), workspace-specific templates, seasons and crop cycles, yield per area, prices and revenue
- [ ] Work and inspection follow-ups: calendar rules (weekdays, months, seasons), per-plant tasks for a location, watering
  routines, location-level work, costs and stock, verification figures on the dashboard
- [ ] Agent follow-ups: retention for `agent_runs`; wire `symptom_cluster` (needs multi-asset issues); validate the
  irrigation thresholds once irrigation logs or soil sensors exist
- [ ] Datasets follow-ups: label export with provenance, retention policy for dataset records

## Waiting for owner decisions
- [ ] Dataset licences: read the official licence pages of the candidates in `docs/datasets/candidates.json` and record
  the evidence; decide PlantDoc (written confirmation from the authors, or keep it excluded); decide the open image-origin
  questions (Cassava, Irish potato, PlantNet); reject PlantVillage in the catalog
- [ ] A qualified plant pathologist to confirm the pending protocol thresholds, and a way to verify a signer's
  qualification (no protocol can be approved before both exist). Disease detection (Stage E) stays blocked until then
- [ ] Hosting: connect GitHub to the Vercel project and set the production branch (HOSTING.md section 9, ADR-051); choose
  an API/worker host, domains, storage provider and a staging database (HOSTING.md section 10, STAGING.md section 8); then
  replace the Preview `VITE_API_BASE_URL` placeholder
- [ ] Zero-cost option (ZERO_COST.md): API on Vercel Functions and a daily Vercel Cron tick endpoint, after verifying the
  free-tier facts in section 6 (needs approval to create the Vercel API project)
- [ ] Take and rehearse the first real backup of the Supabase database (needs PostgreSQL 17 client tools)

## Later (production readiness)
- [ ] Verify the S3 storage adapter against a real bucket (`python -m app.tools.storage_check`) and run the evidence
  reconciler once there
- [ ] Purge job and retention policy for soft-deleted photo files
- [ ] Error reporting and alerting; database-backed worker heartbeat for hosts without exec health checks; a single-step
  guard around `alembic upgrade`
- [ ] Local PostgreSQL+PostGIS (or Docker) for developers, so the whole suite runs locally on PostgreSQL
- [ ] Revisit the unindexed-foreign-key notices with real query statistics
- [ ] Optional: a separate Supabase project or branch for tests
- [ ] OpenAPI client drift check in CI
- [ ] An event bus, if a second consumer of domain events appears (the worker covers today's scheduled jobs)

## Done (condensed; details in CURRENT_STATE.md)
- [x] Foundation: documentation and PRD, Stage-2 deck, rules proof of concept, hosted PostgreSQL+PostGIS on Supabase
  (ADR-015), monorepo, Alembic with PostGIS, RLS on every table, CI green on GitHub including the full suite on PostgreSQL
- [x] Identity and tenancy: accounts (argon2id, JWT, refresh), login throttling, request IDs, audit trail, workspaces with
  two modes, five roles, tenant isolation suite covering every workspace endpoint, member management in the app (ADR-074)
- [x] Assets: locations, species catalog with workspace species, individual plants and crop batches, lifecycle events,
  exits and corrections (ADR-055), Trees/Plants/Crop batches/Species/Crops/Fields and zones pages (ADR-063, ADR-078)
- [x] Monitoring: observations with the state projection (rebuildable), photo evidence with local and S3 storage
  (ADR-052, ADR-054), growth measurements, health and growth over time (ADR-066), map with layers, weather (Open-Meteo,
  ADR-065) with place search and saved places (ADR-075), "Use my location" (ADR-079)
- [x] Operations: issue workflows with evidence, history and resolution; tasks with history; recorded work and the
  "did it help?" check (ADR-059); recurring inspections (ADR-062); harvests with corrections and the Yield KPI (ADR-056)
- [x] Agent: four rules including the advisory `irrigation_defer`, suggestions inbox, scheduled worker, run history, rule
  versions (Stage C, ADR-039..042)
- [x] Reports: Analytics and Impact for a period, print and CSV, with a summary sentence (ADR-068, ADR-077)
- [x] Future surfaces behind CapabilityGate and the Coming next page; no model is claimed anywhere
- [x] Data and ML foundations: dataset catalog with licence verification, review queue, quality checks, grouped splits,
  evaluation harness, reviewer agreement, claim gate, sample import, evaluation-protocol registry with sign-offs
  (Stage D, ADR-044..050)
- [x] Platform: Dockerfiles and compose stack, deployment and backup/restore docs with CI proof, container lint and image
  scan in CI, UTC timestamps everywhere (ADR-060), non-commercial licensing decision (ADR-065)
- [x] Local demo with real weather, background worker and two tours; example data for the development database
  (ADR-061, ADR-064, ADR-067)
- [x] English and Hindi on every screen (ADR-058)
- [x] Field Ledger redesign, phases 1–6 (ADR-069 to ADR-077), with the gaps list in `docs/REDESIGN_GAPS.md`
- [x] README for the repository
