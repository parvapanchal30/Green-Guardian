# GreenGuardian

An operating system for managing biological assets (trees, crops, batches, fields, parks) through their lifecycle: register → observe → detect → issue → task → action → verify → predict → recommend.

**Read first, in order:** `docs/PRODUCT_VISION.md`, `docs/CURRENT_STATE.md`, `docs/TODO.md`, then `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/DOMAIN_MODEL.md`. Other docs in `docs/` are referenced from those.

## Non-negotiables
- Tenant scoping: every tenant query goes through a workspace-scoped repository; add isolation tests for every endpoint.
- State is time-aware: observations, health/growth records, lifecycle events and status histories are append-only.
- AI honesty: label RULE / STATISTICAL / MODEL / LLM; never show mock predictions as real; future features sit behind `CapabilityGate`.
- Green Management and Agricultural Production are modes of ONE model, not two apps.
- Secrets only in env; `.env.example` holds names only.
- When you make an architectural/product decision: implement, update the relevant doc, add a `docs/DECISION_LOG.md` entry. Update `docs/CURRENT_STATE.md` and `docs/TODO.md` at session end.
- Commits: `feat:`/`fix:`/`refactor:`/`docs:`/`test:`/`chore:`; small and meaningful; no secrets or build output.
