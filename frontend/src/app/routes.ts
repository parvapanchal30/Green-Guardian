import type { Role, Stage, WorkspaceMode } from '../api/types'
import { atLeast } from '../lib/format'

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
  { path: 'assets/trees', label: 'Trees', group: 'Assets', status: 'building', stage: 'mvp', modes: [G], summary: 'Individually tracked trees.' },
  { path: 'assets/plants', label: 'Plants', group: 'Assets', status: 'building', stage: 'mvp', summary: 'Individually tracked plants.' },
  { path: 'assets/crops', label: 'Crops', group: 'Assets', status: 'building', stage: 'mvp', modes: [A], summary: 'Crops grown in this workspace.' },
  { path: 'assets/batches', label: 'Batches', group: 'Assets', status: 'building', stage: 'mvp', modes: [A], summary: 'Crop batches tracked as populations.' },
  { path: 'assets/species', label: 'Species', group: 'Assets', status: 'building', stage: 'mvp', summary: 'Species and crop catalog with lifecycle templates.' },
  { path: 'locations', label: 'Fields and zones', group: 'Assets', status: 'building', stage: 'mvp', summary: 'Spatial structure of the workspace.' },

  { path: 'tasks', label: 'Tasks', group: 'Work', status: 'live', stage: 'mvp', summary: 'Assigned work with due dates, priorities and history.' },
  { path: 'issues', label: 'Botanical issues', group: 'Work', status: 'live', stage: 'mvp', summary: 'Structured issues with severity, evidence, workflow and resolution.' },
  { path: 'inspections', label: 'Inspections', group: 'Work', status: 'building', stage: 'mvp', summary: 'Scheduled and ad-hoc inspections.' },
  { path: 'harvests', label: 'Harvests', group: 'Work', status: 'building', stage: 'mvp', modes: [A], summary: 'Harvest records and plans.' },

  { path: 'monitor/health', label: 'Health', group: 'Monitor', status: 'building', stage: 'mvp', summary: 'Current and historical health of assets.' },
  { path: 'monitor/growth', label: 'Growth', group: 'Monitor', status: 'building', stage: 'mvp', summary: 'Recorded growth over time.' },
  { path: 'monitor/weather', label: 'Weather', group: 'Monitor', status: 'live', summary: 'Forecast context for a location.' },
  { path: 'monitor/map', label: 'Map', group: 'Monitor', status: 'live', stage: 'mvp', summary: 'Assets, health, issues and tasks on a map.' },
  { path: 'monitor/yield', label: 'Yield', group: 'Monitor', status: 'soon', modes: [A], capability: 'yield_prediction', stage: 'v2', technique: 'Machine learning', summary: 'Production forecast with a range and confidence, updated as observations arrive.' },
  { path: 'monitor/irrigation', label: 'Irrigation', group: 'Monitor', status: 'soon', capability: 'irrigation_recommendation', stage: 'v3', technique: 'Water balance + rules', summary: 'Recommended volume and time window from soil moisture, forecast, crop and growth stage.' },

  { path: 'ai/agent', label: 'Botanical Operations Agent', group: 'AI', status: 'live', summary: 'Rule-based checks that turn recorded observations into explained suggestions.' },
  { path: 'ai/datasets', label: 'Datasets', group: 'AI', status: 'live', summary: 'Catalog of data sources with licence evidence, label review, quality checks and the claim gate. No model is trained here.' },
  { path: 'ai/crop-recommendation', label: 'Crop Recommendation', group: 'AI', status: 'soon', modes: [A], capability: 'crop_recommendation', stage: 'v3', technique: 'Recommendation engine', summary: 'Soil, weather, location, water, season and market in; ranked crops with yield, cost and profit ranges out.' },
  { path: 'ai/disease-detection', label: 'Disease Detection', group: 'AI', status: 'soon', capability: 'disease_detection', stage: 'v2', technique: 'Computer vision', summary: 'Image in; possible condition, confidence and severity out; one click to create a botanical issue.' },
  { path: 'ai/growth-prediction', label: 'Growth Prediction', group: 'AI', status: 'soon', capability: 'growth_prediction', stage: 'v2', technique: 'Machine learning', summary: 'Historical observations plus environment in; predicted growth trajectory with an uncertainty band out.' },
  { path: 'ai/survival-prediction', label: 'Survival Prediction', group: 'AI', status: 'soon', modes: [G], capability: 'survival_prediction', stage: 'v2', technique: 'Machine learning', summary: 'Health, environment and history in; survival probability and ranked risk factors out.' },
  { path: 'ai/yield-prediction', label: 'Yield Prediction', group: 'AI', status: 'soon', modes: [A], capability: 'yield_prediction', stage: 'v2', technique: 'Machine learning', summary: 'Plant population, health, growth and environment in; expected yield range out.' },
  { path: 'ai/harvest-prediction', label: 'Harvest Prediction', group: 'AI', status: 'soon', modes: [A], capability: 'harvest_prediction', stage: 'v2', technique: 'Machine learning', summary: 'Growth stage and maturity indicators in; harvest window out.' },

  { path: 'reports/analytics', label: 'Analytics', group: 'Reports', status: 'building', stage: 'mvp', summary: 'Reports generated from underlying records.' },
  { path: 'reports/impact', label: 'Impact', group: 'Reports', status: 'building', stage: 'mvp', modes: [G], summary: 'Plantation, survival, health, growth and coverage impact.' },
  { path: 'reports/financials', label: 'Financials', group: 'Reports', status: 'soon', modes: [A], capability: 'profitability', stage: 'v3', technique: 'Financial model', summary: 'Yield, cost and market price in; revenue and profit ranges out.' },

  { path: 'settings/members', label: 'Members', group: 'Settings', status: 'live', summary: 'People and roles in this workspace.' },
  { path: 'settings/audit', label: 'Audit log', group: 'Settings', status: 'live', minRole: 'manager', summary: 'Who did what, when, from where. Read-only.' },
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

export const pathFor = (ws: string, r: NavRoute) => `/w/${ws}${r.path ? `/${r.path}` : ''}`
