# Current State

_Last updated: 2026-10-06 (initial session)_

## Repository
- GitHub: `parvapanchal30/Green-Guardian` — **was empty** (no commits) at start. Cloned to `D:\college\GreenGuardian`.
- Contents now: `docs/` only (project memory + PRD). **No application code yet.**

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
