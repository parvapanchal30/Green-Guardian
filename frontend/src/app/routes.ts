import type { Role, Stage, WorkspaceMode } from '../api/types'
import type { TKey } from '../i18n'
import { atLeast } from '../lib/format'
import type { IconName } from '../components/icon-set'

/**
 * Navigation registry (docs/PRD.md section 16).
 *
 * status:
 *  - live:     implemented end to end
 *  - building: part of the MVP, UI/API not finished yet ("In development")
 *  - soon:     planned for V2+ ("Coming soon"); gated by a backend capability and never shows fabricated output
 */
export type RouteStatus = 'live' | 'building' | 'soon'

export interface NavRoute {
  /** path segment under /w/:ws */
  path: string
  label: string
  group: 'Home' | 'Assets' | 'Work' | 'Monitor' | 'AI' | 'Reports' | 'Settings'
  status: RouteStatus
  /** only shown for these modes; omitted = all modes */
  modes?: WorkspaceMode[]
  /** minimum workspace role that sees this entry in the navigation (the server enforces it independently) */
  minRole?: Role
  /** backend capability key that gates a `soon` surface */
  capability?: string
  stage?: Stage
  technique?: string
  summary?: string
}

const G: WorkspaceMode = 'green_management'
const A: WorkspaceMode = 'agricultural_production'

export const ROUTES: NavRoute[] = [
  { path: '', label: 'Home', group: 'Home', status: 'live' },

  { path: 'assets', label: 'All assets', group: 'Assets', status: 'live', stage: 'mvp', summary: 'Registry of every tree, plant, crop batch, field and zone.' },
  { path: 'assets/trees', label: 'Trees', group: 'Assets', status: 'live', stage: 'mvp', modes: [G], summary: 'Individually tracked trees.' },
  { path: 'assets/plants', label: 'Plants', group: 'Assets', status: 'live', stage: 'mvp', summary: 'Individually tracked plants.' },
  { path: 'assets/crops', label: 'Crops', group: 'Assets', status: 'live', stage: 'mvp', modes: [A], summary: 'Crops grown in this workspace.' },
  { path: 'assets/batches', label: 'Batches', group: 'Assets', status: 'live', stage: 'mvp', modes: [A], summary: 'Crop batches tracked as populations.' },
  { path: 'assets/species', label: 'Species', group: 'Assets', status: 'live', stage: 'mvp', summary: 'Species and crop catalog with lifecycle templates.' },
  { path: 'locations', label: 'Fields and zones', group: 'Assets', status: 'live', stage: 'mvp', summary: 'Spatial structure of the workspace.' },

  { path: 'tasks', label: 'Tasks', group: 'Work', status: 'live', stage: 'mvp', summary: 'Assigned work with due dates, priorities and history.' },
  { path: 'issues', label: 'Botanical issues', group: 'Work', status: 'live', stage: 'mvp', summary: 'Structured issues with severity, evidence, workflow and resolution.' },
  { path: 'inspections', label: 'Inspections', group: 'Work', status: 'live', stage: 'mvp', summary: 'Scheduled and ad-hoc inspections.' },
  { path: 'harvests', label: 'Harvests', group: 'Work', status: 'live', stage: 'mvp', modes: [A], summary: 'Harvest records and plans.' },

  { path: 'monitor/health', label: 'Health', group: 'Monitor', status: 'live', stage: 'mvp', summary: 'Current and historical health of assets.' },
  { path: 'monitor/growth', label: 'Growth', group: 'Monitor', status: 'live', stage: 'mvp', summary: 'Recorded growth over time.' },
  { path: 'monitor/weather', label: 'Weather', group: 'Monitor', status: 'live', summary: 'Forecast context for a location.' },
  { path: 'monitor/map', label: 'Map', group: 'Monitor', status: 'live', stage: 'mvp', summary: 'Assets, health, issues and tasks on a map.' },
  { path: 'monitor/yield', label: 'Yield', group: 'Monitor', status: 'soon', modes: [A], capability: 'yield_prediction', stage: 'v2', technique: 'Machine learning', summary: 'Production forecast with a range and confidence, updated as observations arrive.' },
  { path: 'monitor/irrigation', label: 'Irrigation', group: 'Monitor', status: 'soon', capability: 'irrigation_recommendation', stage: 'v3', technique: 'Water balance + rules', summary: 'Recommended volume and time window from soil moisture, forecast, crop and growth stage.' },

  { path: 'ai/agent', label: 'Botanical Operations Agent', group: 'AI', status: 'live', summary: 'Rule-based checks that turn recorded observations into explained suggestions.' },
  { path: 'ai/datasets', label: 'Datasets', group: 'AI', status: 'live', summary: 'Catalog of data sources with licence evidence, label review, quality checks and the claim gate. No model is trained here.' },
  { path: 'ai/protocols', label: 'Evaluation protocols', group: 'AI', status: 'live', summary: 'Plans for evaluating a future model, fixed before training, with sign-offs. None is approved.' },
  { path: 'ai/crop-recommendation', label: 'Crop Recommendation', group: 'AI', status: 'soon', modes: [A], capability: 'crop_recommendation', stage: 'v3', technique: 'Recommendation engine', summary: 'Soil, weather, location, water, season and market in; ranked crops with yield, cost and profit ranges out.' },
  { path: 'ai/disease-detection', label: 'Disease Detection', group: 'AI', status: 'soon', capability: 'disease_detection', stage: 'v2', technique: 'Computer vision', summary: 'Image in; possible condition, confidence and severity out; one click to create a botanical issue.' },
  { path: 'ai/growth-prediction', label: 'Growth Prediction', group: 'AI', status: 'soon', capability: 'growth_prediction', stage: 'v2', technique: 'Machine learning', summary: 'Historical observations plus environment in; predicted growth trajectory with an uncertainty band out.' },
  { path: 'ai/survival-prediction', label: 'Survival Prediction', group: 'AI', status: 'soon', modes: [G], capability: 'survival_prediction', stage: 'v2', technique: 'Machine learning', summary: 'Health, environment and history in; survival probability and ranked risk factors out.' },
  { path: 'ai/yield-prediction', label: 'Yield Prediction', group: 'AI', status: 'soon', modes: [A], capability: 'yield_prediction', stage: 'v2', technique: 'Machine learning', summary: 'Plant population, health, growth and environment in; expected yield range out.' },
  { path: 'ai/harvest-prediction', label: 'Harvest Prediction', group: 'AI', status: 'soon', modes: [A], capability: 'harvest_prediction', stage: 'v2', technique: 'Machine learning', summary: 'Growth stage and maturity indicators in; harvest window out.' },

  { path: 'reports/analytics', label: 'Analytics', group: 'Reports', status: 'live', stage: 'mvp', summary: 'Reports generated from underlying records.' },
  { path: 'reports/impact', label: 'Impact', group: 'Reports', status: 'live', stage: 'mvp', modes: [G], summary: 'Plantation, survival, health, growth and coverage impact.' },
  { path: 'reports/financials', label: 'Financials', group: 'Reports', status: 'soon', modes: [A], capability: 'profitability', stage: 'v3', technique: 'Financial model', summary: 'Yield, cost and market price in; revenue and profit ranges out.' },

  { path: 'settings/members', label: 'Members', group: 'Settings', status: 'live', summary: 'People and roles in this workspace.' },
  { path: 'settings/audit', label: 'Audit log', group: 'Settings', status: 'live', minRole: 'manager', summary: 'Who did what, when, from where. Read-only.' },

  { path: 'coming-next', label: 'Coming next', group: 'Home', status: 'live', summary: 'What is live today and what is planned, with what is already recorded for it.' },
]

export const GROUP_ORDER: NavRoute['group'][] = ['Home', 'Assets', 'Work', 'Monitor', 'AI', 'Reports', 'Settings']

export function navFor(mode: WorkspaceMode, role: Role = 'owner'): { group: NavRoute['group']; items: NavRoute[] }[] {
  const visible = ROUTES.filter((r) => (!r.modes || r.modes.includes(mode)) && (!r.minRole || atLeast(role, r.minRole)))
  return GROUP_ORDER.map((group) => ({ group, items: visible.filter((r) => r.group === group) })).filter((g) => g.items.length)
}

export function statusLabel(r: Pick<NavRoute, 'status' | 'stage'>): string | null {
  if (r.status === 'building') return 'In development'
  if (r.status === 'soon') return r.stage === 'mvp' ? 'In development' : `Coming soon · ${r.stage?.toUpperCase()}`
  return null
}

/** Catalog keys for a route's navigation label and summary (the English text above is the source). */
const keyPath = (r: Pick<NavRoute, 'path'>) => (r.path || 'home').replace(/\//g, '.')
export const routeKey = (r: Pick<NavRoute, 'path'>) => `nav.route.${keyPath(r)}` as TKey
export const routeSummaryKey = (r: Pick<NavRoute, 'path'>) => `nav.summary.${keyPath(r)}` as TKey

export const pathFor = (ws: string, r: NavRoute) => `/w/${ws}${r.path ? `/${r.path}` : ''}`

// ------------------------------------------------------------------ the Field Ledger menu (ADR-069, phase 2)

/** Live counts shown beside a menu entry (from the dashboard read model). */
export type NavBadge = 'tasks' | 'issues' | 'suggestions'

export interface NavItem {
  id: string
  /** where the entry goes, under /w/:ws */
  path: string
  icon: IconName
  label: TKey
  /** other pages that belong to this entry (its tabs and detail pages are matched by prefix) */
  also?: string[]
  modes?: WorkspaceMode[]
  minRole?: Role
  badge?: NavBadge
}

export interface NavSection {
  id: 'today' | 'plants' | 'work' | 'monitor' | 'insight'
  label?: TKey
  items: NavItem[]
}

const SOON_PATHS = ROUTES.filter((r) => r.status === 'soon').map((r) => r.path)

/**
 * Only pages that work today are in the menu (planned ones are reached from "Coming next"). Sub-pages such as Trees,
 * Growth, Impact or the audit log are tabs on their entry's page (see SECTIONS).
 */
export const MENU: NavSection[] = [
  { id: 'today', items: [{ id: 'today', path: '', icon: 'today', label: 'navx.today' }] },
  {
    id: 'plants',
    label: 'navx.group.plants',
    items: [
      { id: 'assets', path: 'assets', icon: 'assets', label: 'navx.assets' },
      { id: 'species', path: 'assets/species', icon: 'species', label: 'nav.route.assets.species' },
      { id: 'zones', path: 'locations', icon: 'zones', label: 'nav.route.locations' },
    ],
  },
  {
    id: 'work',
    label: 'navx.group.work',
    items: [
      { id: 'tasks', path: 'tasks', icon: 'tasks', label: 'nav.route.tasks', badge: 'tasks' },
      { id: 'issues', path: 'issues', icon: 'issues', label: 'navx.issues', badge: 'issues' },
      { id: 'inspections', path: 'inspections', icon: 'inspections', label: 'nav.route.inspections' },
      { id: 'harvests', path: 'harvests', icon: 'harvests', label: 'nav.route.harvests', modes: [A] },
    ],
  },
  {
    id: 'monitor',
    label: 'navx.group.monitor',
    items: [
      { id: 'health', path: 'monitor/health', icon: 'health', label: 'navx.healthGrowth', also: ['monitor/growth'] },
      { id: 'map', path: 'monitor/map', icon: 'map', label: 'nav.route.monitor.map' },
      { id: 'weather', path: 'monitor/weather', icon: 'weather', label: 'nav.route.monitor.weather' },
    ],
  },
  {
    id: 'insight',
    label: 'navx.group.insight',
    items: [
      { id: 'agent', path: 'ai/agent', icon: 'agent', label: 'navx.agent', badge: 'suggestions' },
      { id: 'reports', path: 'reports/analytics', icon: 'reports', label: 'navx.reports', also: ['reports'] },
      { id: 'datasets', path: 'ai/datasets', icon: 'datasets', label: 'nav.route.ai.datasets' },
      { id: 'protocols', path: 'ai/protocols', icon: 'protocols', label: 'navx.protocols' },
    ],
  },
]

/** Kept apart at the foot of the menu. */
export const MENU_FOOTER: NavItem[] = [
  { id: 'coming', path: 'coming-next', icon: 'comingNext', label: 'navx.comingNext', also: SOON_PATHS },
  { id: 'settings', path: 'settings/members', icon: 'settings', label: 'navx.settings', also: ['settings'] },
]

const visibleItem = (i: NavItem, mode: WorkspaceMode, role: Role) => (!i.modes || i.modes.includes(mode)) && (!i.minRole || atLeast(role, i.minRole))

export function menuFor(mode: WorkspaceMode, role: Role = 'owner'): { sections: NavSection[]; footer: NavItem[] } {
  return {
    sections: MENU.map((s) => ({ ...s, items: s.items.filter((i) => visibleItem(i, mode, role)) })).filter((s) => s.items.length),
    footer: MENU_FOOTER.filter((i) => visibleItem(i, mode, role)),
  }
}

const matches = (rel: string, p: string) => (p === '' ? rel === '' : rel === p || rel.startsWith(`${p}/`))

/**
 * The menu entry for a page: the entry whose own path (or one of its `also` paths) matches the page most specifically.
 * So /assets/species marks Species, not Assets, and /assets/<id> marks Assets.
 */
export function activeItemId(relPath: string, items: NavItem[]): string | null {
  let best: { id: string; len: number } | null = null
  for (const item of items)
    for (const p of [item.path, ...(item.also ?? [])])
      if (matches(relPath, p) && (!best || p.length > best.len)) best = { id: item.id, len: p.length }
  return best?.id ?? null
}

/** Groups of pages shown as tabs on each other's page. */
export const SECTIONS: string[][] = [
  ['assets', 'assets/trees', 'assets/plants', 'assets/batches', 'assets/crops'],
  ['monitor/health', 'monitor/growth'],
  ['reports/analytics', 'reports/impact', 'reports/financials'],
  ['settings/members', 'settings/audit'],
]

/** The tabs for the page at `relPath`, or null when it is not one of a group's pages (detail pages have no tabs). */
export function sectionTabs(relPath: string, mode: WorkspaceMode, role: Role = 'owner'): NavRoute[] | null {
  const section = SECTIONS.find((s) => s.includes(relPath))
  if (!section) return null
  const tabs = section
    .map((p) => ROUTES.find((r) => r.path === p))
    .filter((r): r is NavRoute => !!r && (!r.modes || r.modes.includes(mode)) && (!r.minRole || atLeast(role, r.minRole)))
  return tabs.length > 1 ? tabs : null
}
