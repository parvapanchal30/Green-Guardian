# Design system: Field Ledger

The look of GreenGuardian, decided in October 2026 (ADR-069). The reference designs live on two design canvases:

- Field Ledger, every page plus the chosen ideas: https://claude.ai/artifact/WpyeUqYPPgnfHtJS2pu1yD (page "Field Ledger")
- The remaining pages (sign-in, workspaces, species, fields and zones, inspections, issues, analytics, datasets,
  protocols, members, audit): https://claude.ai/artifact/8GXaQavve3mzKxr5Tt1P89

Field Ledger reads like a careful field register: slab headings, plain body text, record keys in a monospaced face,
moss green for action, soil brown for labels, and status colours used only for status.

## Typefaces (bundled, SIL Open Font Licence)

| Role | Face | Where | Notes |
|---|---|---|---|
| Body | Hind 400 / 500 / 600 | everything | Latin and Devanagari |
| Headings | Zilla Slab 600 / 700 | `h1`–`h3`, figures (`font-display`) | Latin only |
| Hindi headings | Martel 700 | through the heading stack | only the Devanagari subset is bundled |
| Keys and codes | JetBrains Mono 400 / 500 | `font-mono`: GG-001, T-004, N-102, request IDs | |

The heading stack is `"Zilla Slab", "Martel", Georgia, serif`: the browser takes each letter from the first face that has
it, so English and numbers come from Zilla Slab and Hindi letters from Martel. Hindi headings get a taller line height
(`:lang(hi) h1`). Fonts are imported in `src/styles/fonts.ts` and served from the app itself, so the build's
Content-Security-Policy (`font-src 'self'`) needs no change; a font file is only downloaded when a page uses it.

Type scale: page title 32 px bold display; section title 19 px semibold display; body 15 px; labels and notes 12–13 px;
eyebrows 11 px mono, upper case, 0.08 em tracking, in soil.

## Colour tokens (`src/index.css`)

| Token | Light | Use |
|---|---|---|
| `canvas` | #f3f5f0 | page background |
| `surface` / `surface-2` | #ffffff / #eaeee7 | cards / hover, selected rows |
| `line` / `line-soft` | #d6ddd2 / #e8ece5 | borders / row dividers |
| `ink` / `ink-2` / `ink-3` | #17211b / #48544c / #5b675f | text, secondary text, notes |
| `moss` (+ `moss-ink`, `moss-soft`) | #2f5d3a | primary actions, selection |
| `soil` | #7a5c3e | eyebrows, small labels |
| `healthy`, `at-risk`, `critical` (+ `-soft`) | #23683f, #8a5708, #a8231c | status only |
| `info` (+ `-soft`) | #2c5d82 | weather and neutral information |
| `soon` | #56626e | planned features |

Every text colour reaches 4.5:1 against canvas, surface and surface-2, and every status colour against its soft fill, in
light and dark; `src/test/design-system.test.tsx` checks this from the CSS itself, so a token change that breaks
contrast fails the tests. Dark values apply when the device is dark (unless light is chosen) and when
`data-theme="dark"` is set (the switch arrives with the account menu).

Status is never colour alone: chips carry a shape (● healthy, ▲ at risk, ■ critical, ◌ planned, ◐ in progress) and a word.

## Icons

Lucide (ISC licence), through `src/components/icons.tsx`. Icons are named by meaning (`issues`, `record`, `weather`), not
by picture, in `src/components/icon-set.ts`. They are decoration beside text and hidden from screen readers; an icon-only
button must have its own `aria-label`.

## Building blocks

| Component | File | Use |
|---|---|---|
| `PageHeader` (`eyebrow`, `title`, `subtitle`, actions) | `components/domain.tsx` | top of every page |
| `btn`, `btnPrimary`, `input` | `components/domain.tsx` | buttons and inputs |
| `StatusChip`, `HealthChip`, `SeverityChip`, … | `components/StatusChip.tsx`, `domain.tsx` | status |
| `Tag` | `components/ui.tsx` | record keys in mono (GG-001) |
| `Card`, `SectionHeading` | `components/ui.tsx` | sections |
| `StatTile` | `components/ui.tsx` | one figure with its basis |
| `Segmented` | `components/ui.tsx` | view switches and filters (aria-pressed) |
| `FilterBar` | `components/ui.tsx` | a page's filters on one wrapping row |
| `HealthBar` | `components/ui.tsx` | living plants by band, with a spoken summary |
| `EmptyState` (`icon`) | `components/states.tsx` | what to do when there is nothing yet |

## Rollout

1. **Foundations** (done): typefaces, tokens, icons, the building blocks above. Existing pages pick up the new faces,
   colours, chips, buttons and page titles without moving anything.
2. **Frame and navigation** (done, ADR-070): grouped menu with icons and counts (`MENU` in `app/routes.ts`), sub-pages
   as tabs (`SECTIONS`), Coming next page, search (`components/shell/SearchBox.tsx`), account menu with language and
   light/dark (`lib/theme.ts`), phone bottom bar with Record (`components/shell/BottomBar.tsx`, `RecordPicker.tsx`).
3. **Home** (done, ADR-071): decisions first (icons by rule), rule-built summary sentence (`lib/summary.ts`), figures
   with the health bar, activity by day, due next.
4. **Plant page and recording** (done, ADR-072): photo header, facts strip, health-and-photos chart
   (`asset/HealthChart.tsx`), filterable timeline, side cards, one Record sheet (`asset/RecordSheet.tsx`).

Gaps found along the way are collected in docs/REDESIGN_GAPS.md, one section per phase.
5. **Lists** (done, ADR-073): one list pattern (`LedgerTable`, `SearchField`, `FilterSelect` in `components/ui.tsx`;
   the table becomes cards on phones), photo cards on the Trees, Plants and Crop batches tabs (`asset/AssetCard.tsx`),
   Tasks grouped by due date (`dueGroup` in `lib/summary.ts`), Issues scopes including "Waiting for a check".
6. **Everything else** (done, ADR-074 to ADR-077): sign-in and workspaces, members and audit log, weather in two tabs
   (`weather/WeatherChart.tsx`, `weather/PinMap.tsx`, `dailyForecast` / `rainAdvice` in `lib/weather.ts`), health,
   growth, map, reports (summary sentence, `analyticsSentence` / `impactSentence` in `lib/summary.ts`), agent,
   datasets, protocols. Page group labels are `eyebrow.*`; headings are styled in the CSS base layer.
