import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { GrowthMonitor, HealthMonitor } from '../lib/monitor'

const state = vi.hoisted(() => ({ health: null as unknown, growth: null as unknown, growthArgs: [] as unknown[][], weeks: [] as number[], series: [] as unknown[] }))

vi.mock('../lib/monitor', async (orig) => ({
  ...(await orig<typeof import('../lib/monitor')>()),
  useHealthMonitor: (_ws: string, weeks: number) => {
    state.weeks.push(weeks)
    return { isLoading: false, error: null, data: state.health, refetch: vi.fn() }
  },
  useGrowthMonitor: (_ws: string, metric: string, months: number) => {
    state.growthArgs.push([metric, months])
    return { isLoading: false, error: null, data: state.growth, refetch: vi.fn() }
  },
  useAssetGrowth: () => ({ isLoading: false, data: { asset_id: 'a1', measurements: state.series } }),
}))
vi.mock('../app/WorkspaceLayout', () => ({
  useWorkspaceCtx: () => ({ ws: 'w1', workspace: { id: 'w1', mode: 'green_management', role: 'viewer' }, capabilities: [] }),
}))

import { I18nProvider } from '../i18n'
import { GrowthPage, GrowthPanel } from '../pages/GrowthPage'
import { HealthPage } from '../pages/HealthPage'

const week = (start: string, over = {}) => ({ week_start: start, observations: 0, assets: 0, mean_score: null, healthy: 0, at_risk: 0, critical: 0, ...over })
const healthData: HealthMonitor = {
  method: 'statistical', weeks: 2,
  now: { healthy: 3, at_risk: 1, critical: 1, no_data: 2 },
  weekly: [week('2026-10-12T00:00:00Z'), week('2026-10-19T00:00:00Z', { observations: 4, assets: 3, mean_score: 61.5, healthy: 2, at_risk: 1, critical: 1 })],
  declining: [{ asset_id: 'a2', label: 'Neem #102', first_score: 78, first_at: '2026-09-01T00:00:00Z', latest_score: 31, latest_at: '2026-10-20T00:00:00Z', change: -47 }],
  not_observed_days: 30, not_observed_count: 1,
  not_observed: [{ asset_id: 'a3', label: 'Gulmohar #12', last_observed_at: null }],
}
const growthData: GrowthMonitor = {
  method: 'statistical', metric: 'height_cm', months: 12, min_span_days: 30, measured_assets: 2, comparable_assets: 1, median_change_pct: 30,
  assets: [
    { asset_id: 'a1', label: 'Neem #101', kind: 'tree', measurements: 2, first: 100, first_at: '2026-08-01T00:00:00Z', latest: 130, latest_at: '2026-10-01T00:00:00Z', change: 30, change_pct: 30, per_year: 179.5 },
    { asset_id: 'a4', label: 'Sapling', kind: 'tree', measurements: 1, first: 40, first_at: '2026-10-01T00:00:00Z', latest: 40, latest_at: '2026-10-01T00:00:00Z', change: null, change_pct: null, per_year: null },
  ],
}

beforeEach(() => {
  state.health = healthData
  state.growth = growthData
  state.weeks = []
  state.growthArgs = []
  state.series = []
})

describe('health over time', () => {
  it('shows current bands, each week, the steepest declines and assets nobody has looked at', async () => {
    render(<MemoryRouter><HealthPage /></MemoryRouter>)
    expect(screen.getByText('Statistical')).toBeInTheDocument()
    const weeks = within(screen.getByRole('list', { name: 'Week by week' })).getAllByRole('listitem')
    expect(weeks[0]).toHaveTextContent('no scores')
    expect(weeks[1]).toHaveTextContent('4 scores · mean 61.5')
    expect(screen.getByRole('link', { name: 'Neem #102' }).closest('li')).toHaveTextContent('78 → 31')
    expect(screen.getByRole('link', { name: 'Gulmohar #12' }).closest('li')).toHaveTextContent('never observed')
    await userEvent.click(screen.getByRole('button', { name: '52 weeks' }))
    expect(state.weeks.at(-1)).toBe(52)
  })

  it('says when there is nothing to show', () => {
    state.health = { ...healthData, now: { healthy: 0, at_risk: 0, critical: 0, no_data: 0 } }
    render(<MemoryRouter><HealthPage /></MemoryRouter>)
    expect(screen.getByText('No living assets yet')).toBeInTheDocument()
  })
})

describe('growth', () => {
  it('compares recorded measurements and says when a second one is still needed', async () => {
    render(<MemoryRouter><GrowthPage /></MemoryRouter>)
    expect(screen.getByText(/Median change 30% across 1 assets/)).toBeInTheDocument()
    const rows = within(screen.getByRole('table')).getAllByRole('row')
    expect(rows[1]).toHaveTextContent('+30 cm (30%)')
    expect(rows[2]).toHaveTextContent('needs another measurement')
    await userEvent.selectOptions(screen.getByLabelText('Measurement'), 'canopy_m')
    expect(state.growthArgs.at(-1)).toEqual(['canopy_m', 12])
  })

  it('the asset panel lists measurements and invites the first one', () => {
    const { rerender } = render(<GrowthPanel ws="w1" assetId="a1" />)
    expect(screen.getByText(/No measurements yet/)).toBeInTheDocument()
    state.series = [
      { observation_id: 'o1', observed_at: '2026-08-01T00:00:00Z', height_cm: 100, girth_cm: 20, canopy_m: null },
      { observation_id: 'o2', observed_at: '2026-10-01T00:00:00Z', height_cm: 130, girth_cm: null, canopy_m: null },
    ]
    rerender(<GrowthPanel ws="w1" assetId="a1" />)
    const list = screen.getByRole('list', { name: 'Measurements' })
    expect(within(list).getAllByRole('listitem')[0]).toHaveTextContent('Height 130 cm') // newest first
  })

  it('renders in Hindi', () => {
    render(<I18nProvider initial="hi"><MemoryRouter><GrowthPage /></MemoryRouter></I18nProvider>)
    expect(screen.getByRole('heading', { name: 'वृद्धि' })).toBeInTheDocument()
  })
})
