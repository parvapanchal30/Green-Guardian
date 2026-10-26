# Frontend Architecture

## Stack
React 18 + TypeScript (strict) + Vite · Tailwind + shadcn/ui (Radix) · React Router (data routers, lazy routes) · TanStack Query · react-hook-form + zod · Recharts · MapLibre GL JS · i18next · Vitest + Testing Library · Playwright.

## Structure
```
src/
  app/            providers (Query, Auth, Workspace, Theme, i18n), router, error boundaries
  api/            generated OpenAPI types + thin fetch client (auth, problem+json → typed errors, refresh)
  features/       assets/ observations/ issues/ tasks/ map/ dashboard/ agent/ reports/ settings/ ai/
                    each: routes, components, hooks (useXQuery), schemas (zod), types
  components/     design-system layer: StatusChip, HealthBadge, LifecycleStepper, SeverityPill, KpiTile,
                  DataTable, EmptyState, ErrorState, Skeletons, CapabilityGate, ComingSoonPanel,
                  UncertaintyBand, MethodBadge(rule|model|llm), AssetPicker, PhotoUploader
  lib/            format, dates (workspace tz), units, geo helpers, a11y utils
  i18n/           en.json (all strings externalized)
```

## Data fetching & caching
- TanStack Query keys: `[workspaceId, resource, params]`. Mutations invalidate by resource family. Optimistic UI **only** for low-risk toggles (task status, dismiss recommendation); never for issue transitions or creation.
- Filters/sort/pagination live in the URL (shareable, back-button safe).
- Every list/detail view implements **loading (skeleton), empty (with next action), error (retry), and forbidden** states — part of Definition of Done.
- Auth: access token in memory, refresh via httpOnly cookie or rotating refresh token; 401 → single-flight refresh → retry.

## Mode-awareness & capabilities
- `WorkspaceContext` supplies `mode` and `capabilities` (from `/capabilities`). A `vocabulary` map renders mode-specific terms (Zone↔Field, Survival↔Harvest KPIs). Navigation is generated from a typed route registry with `{mode[], capability?, status: live|soon}`.
- `<CapabilityGate feature="disease_detection">` renders the live feature if available, else `<ComingSoonPanel technique="Computer vision" />` showing the real layout with disabled controls. **No fabricated results.** Dev-only sample data is behind `VITE_SAMPLE_DATA=true`, watermarked "Sample data", and excluded from production builds.

## Design system principles
The current visual system is **Field Ledger** (ADR-069): typefaces, colour tokens, icons and building blocks are documented in docs/DESIGN_SYSTEM.md.

Dense tables with sticky headers and column control; strong status semantics (color **+** icon **+** text); lifecycle stepper on asset pages; health spectrum scale used consistently (map, tables, badges); biological context always visible (species, zone, stage); explainability components (`MethodBadge`, "Why?" popovers showing rule inputs); uncertainty via bands/ranges (`UncertaintyBand`), not point values. Light/dark themes; earthy-but-neutral palette; avoid generic AI-SaaS gradient aesthetic.

## Key screens (MVP)
Home/Attention · Asset list (table + map split) · Asset profile (state, lifecycle, health/growth charts, timeline, issues, tasks, observations) · Observation form (mobile-first) · Issues board/list + detail (workflow stepper, history, evidence) · Tasks (list, my tasks, calendar-lite) · Map (layer panel, filters, detail drawer) · Dashboards (mode-shaped) · Agent (rules, recommendations inbox, runs) · Reports · Settings · Future surfaces: Crop Recommendation, Disease Detection, Growth/Survival/Yield/Harvest Prediction, Irrigation, Financials.

## Map
`MapView` with a **layer registry** (`id, label, source(query), style, status, requiresCapability`). Sources are GeoJSON from `/map`; clustering client-side below zoom threshold; selection → side drawer. Disabled layers appear in the panel with a "Soon" badge.

## Mobile / field
Responsive from 360 px; bottom-sheet forms; large touch targets; camera capture input; drafts persisted in IndexedDB; failed submissions queued with retry (full offline sync is V2); PWA manifest.

## Accessibility
WCAG 2.1 AA: semantic landmarks, focus management in dialogs/drawers, keyboard-operable map controls with list alternatives, never color-only status, `prefers-reduced-motion`, axe checks in CI.

## Testing
Vitest + RTL for forms (validation, error mapping), workflow components, CapabilityGate; MSW for API mocks (mocks = contract fixtures, not product data); Playwright golden path.

## Implementation status (2026-10-07)
Built: auth (register/login/refresh/logout, session restore), workspace list/create with mode choice, mode-aware app shell with registry-driven navigation (mobile menu), Home (mode KPIs shown as "No data yet", empty attention inbox, live capability table), Weather (real endpoint), Members (read-only), and `CapabilityGate`/`ComingSoonPanel` with real-layout previews for Crop Recommendation and Disease Detection (controls disabled). Every other route renders an honest "In development"/"Coming soon" page. 19 unit tests (API client token refresh, route registry invariants, capability gate fail-closed behaviour, weather summarisation).
Verified in the browser pane against a local dev API: register, login, create an agricultural workspace, home, capability-gated pages (controls effectively disabled), weather with the mock provider, full-reload session restore, and a 375px layout without horizontal scroll. Screenshot-based visual review is still pending because the pane was hidden.

## Vertical slice UI (2026-10-07)

Live pages: **Assets** (list with search/type/health filters, register form with species/zone/coordinates/crop-batch population, add zone/field), **Asset profile** (current state, record observation with optional photo *reference*, suggestions with Why?/Accept/Dismiss, issues, tasks, chronological history), **Botanical issues** (open/closed/all, severity, search), **Issue detail** (workflow stepper showing only stages actually visited, legal transitions only, resolution form with outcome/notes and an explicit "cancel open tasks" choice, evidence, tasks with add-task form, full history), **Tasks** (My tasks / All open / Done; start, block, resume, complete with an optional follow-up health check, manager-only reopen/cancel), **Agent** (rules with parameters and method labels, run checks, open suggestions), **Home** (counts from recorded data, attention inbox, capability table). Buttons that the server would reject for the user's role are hidden; the server remains the authority.
Verified in a real browser against a running API on a throwaway database: the whole loop (register → observe → suggestion → issue → task → complete with follow-up → resolve), the blocked close with an open task, 300 concurrent API requests (no errors), and 375 px layouts for all new pages without horizontal scroll. Component/unit tests: 30.
Known limits: no screenshot-based visual review yet; observation photo upload (reference only); no map; dashboard figures are list totals until `GET /dashboard` exists.

## Screen status (2026-10-17)
| Screen | Status |
|---|---|
| Sign-in, register, workspaces | Fully working |
| Home dashboard (both modes), filters | Fully working |
| Assets list, asset profile (observation form, issues, tasks, history, **photos**) | Fully working |
| Botanical issues list and detail (workflow, tasks, **photos**) | Fully working |
| Tasks | Fully working |
| Botanical Operations Agent (suggestions, rules in force) | Fully working (manual runs; no scheduler) |
| Map | Fully working (basemap tiles: public OSM, set `VITE_MAP_TILE_URL` for production) |
| Weather | Fully working (live Open-Meteo; non-commercial tier) |
| Members | Partially working (list; invite/role UI missing) |
| Audit log (Settings; managers and owners; filters, pagination, request IDs, retention note) | Fully working |
| Trees, Plants, Species, Fields and zones, Inspections, Health, Growth, Reports | Planned or in development (placeholder pages, no fabricated data) |
| Irrigation, Disease Detection, Growth/Survival Prediction, Crop Recommendation, Yield, Harvest | Planned: "Coming soon", gated by `CapabilityGate`, no predictions shown |
