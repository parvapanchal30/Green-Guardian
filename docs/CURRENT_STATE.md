# Current State

_Last updated: 2026-10-06 (initial session)_

## Repository
- GitHub: `parvapanchal30/Green-Guardian` — **was empty** (no commits) at start. Cloned to `D:\college\GreenGuardian`.
- Contents now: `docs/` (project memory + PRD), `pitch/` (Stage-2 review deck + generator), and a small proof of concept: `backend/app/modules/intelligence/rules/` (rules engine) with `backend/tests/` (5 passing tests) and `backend/poc_run.py` (synthetic data run). **No API, database or frontend yet.**

## Audit result
| Question | Answer |
|---|---|
| What works? | Nothing to run — greenfield |
| Retain? | N/A |
| Refactor/remove? | N/A |
| Missing? | Everything: backend, frontend, DB, infra, CI, tests |
| Architectural risks | See ARCHITECTURE §14 |

## Environment (dev machine)
Python 3.13.3, Node 24.14.0 present. **Docker not installed.** PostGIS availability is the first setup blocker (ADR-007). Git identity: `parvapanchal30 <parvampanchal.c@gmail.com>`.

## Decisions made
ADR-001..011 in DECISION_LOG.md (stack, monolith, asset model, append-only history, jobs, modes, PostGIS, capability-gated future surfaces, rules-first agent, auth, template-driven workflows).

## Next
See `TODO.md` — Phase 0 scaffold, then vertical slices per MVP_SCOPE build order.

## Must-not-break (once code exists)
Tenant scoping on all queries · append-only history tables · honest AI labelling · no mock data in prod builds.

## Stage-2 presentation (2026-10-06)
`pitch/GreenGuardian-Stage2-Review.pptx` — 11 slides following the college template (source was a PDF; rebuilt). Regenerate: `cd pitch && npm install && node build_stage2.js`. Slide content mirrors PRD/MVP_SCOPE; solid = MVP, dashed = planned. **Still blank by design:** student names/IEN/guide (slide 1), team member names (slide 9), signed industry approval letter (slide 11). Gantt uses relative weeks W1–W12 with an assumed Stage 3/4 split at W6.
