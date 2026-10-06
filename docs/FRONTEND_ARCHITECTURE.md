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
