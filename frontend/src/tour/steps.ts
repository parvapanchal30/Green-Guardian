import type { Role, WorkspaceMode } from '../api/types'

/**
 * The in-app tour: a short, generic walk through the product for ANY workspace (no demo-specific names). It has the same
 * shape as the automated demo tour in frontend/tour/steps.json (page, highlighted element, and a title and caption that
 * live in the i18n catalogs here), so content can move between the two. A step is shown only when the person's role and the workspace mode make it meaningful.
 */
export interface TourStep {
  /** Title and caption are catalog entries `tour.step.<id>.title` / `.caption` (English and Hindi). */
  id: string
  /** Page inside the workspace, e.g. '/assets'. '' is the dashboard. */
  path: string
  /** CSS selector of the element to highlight once the page has rendered. */
  focus?: string
  /** Open the first asset in the Assets list instead of `path` (asset pages need an asset). */
  openFirstAsset?: boolean
  minRole?: Role
  modes?: WorkspaceMode[]
}

const RANK: Record<Role, number> = { viewer: 0, worker: 1, manager: 2, admin: 3, owner: 4 }

export const STEPS: TourStep[] = [
  {
    id: 'dashboard',
    path: '',
    focus: 'main h1',
  },
  {
    id: 'assets',
    path: '/assets',
    focus: 'table',
  },
  {
    id: 'asset-lifecycle',
    path: '/assets',
    openFirstAsset: true,
    focus: 'section[aria-labelledby=lifecycle]',
  },
  {
    id: 'asset-harvests',
    path: '/assets',
    openFirstAsset: true,
    modes: ['agricultural_production'],
    focus: 'section[aria-labelledby=harvest]',
  },
  {
    id: 'issues',
    path: '/issues',
    focus: 'main h1',
  },
  {
    id: 'tasks',
    path: '/tasks',
    focus: 'main h1',
  },
  {
    id: 'agent',
    path: '/ai/agent',
    focus: 'main h1',
  },
  {
    id: 'map',
    path: '/monitor/map',
    focus: 'main h1',
  },
  {
    id: 'audit',
    path: '/settings/audit',
    minRole: 'manager',
    focus: 'main h1',
  },
  {
    id: 'datasets',
    path: '/ai/datasets',
    focus: 'main h1',
  },
]

export function stepsFor(mode: WorkspaceMode, role: Role): TourStep[] {
  return STEPS.filter((s) => (!s.modes || s.modes.includes(mode)) && RANK[role] >= RANK[s.minRole ?? 'viewer'])
}
