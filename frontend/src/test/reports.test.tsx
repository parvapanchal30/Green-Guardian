import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AnalyticsReport, ImpactReport } from '../lib/reports'

const state = vi.hoisted(() => ({
  since: [] as string[],
  analytics: null as unknown,
  impact: null as unknown,
  csv: vi.fn(),
}))

vi.mock('../lib/reports', async (orig) => ({
  ...(await orig<typeof import('../lib/reports')>()),
  useAnalytics: (_ws: string, since: string) => {
    state.since.push(since)
    return { isLoading: false, error: null, data: state.analytics, refetch: vi.fn() }
  },
  useImpact: (_ws: string, since: string) => {
    state.since.push(since)
    return { isLoading: false, error: null, data: state.impact, refetch: vi.fn() }
  },
}))
vi.mock('../lib/csv', async (orig) => ({ ...(await orig<typeof import('../lib/csv')>()), downloadCsv: state.csv }))
vi.mock('../app/WorkspaceLayout', () => ({
  useWorkspaceCtx: () => ({ ws: 'w1', workspace: { id: 'w1', mode: 'green_management', role: 'viewer' }, capabilities: [] }),
}))

import { AnalyticsPage, ImpactPage } from '../pages/ReportsPages'
import { monthsAgo } from '../lib/reports'

const analytics: AnalyticsReport = {
  method: 'statistical', since: '2025-10-26T00:00:00Z', until: '2026-10-26T00:00:00Z',
  issues: { opened: 4, closed: 3, still_open: 2, opened_by_category: { pest: 3, disease: 1 }, opened_by_severity: { high: 1, low: 3 }, closed_by_outcome: { fixed: 3 }, median_days_to_close: 6.5 },
  tasks: { created: 10, completed: 8, cancelled: 1, completed_with_due_date: 4, completed_on_time: 3, on_time_pct: 75, overdue_now: 2, completed_by_type: { water: 5, treat: 3 } },
  actions: { recorded: 8, by_kind: { water: 5, treat: 3 }, top_products: [{ name: 'Neem oil', count: 3 }] },
  observations: { recorded: 20, with_health_score: 15, with_measurements: 5, assets_observed: 9, observers: 3, by_kind: {} },
  agent: { suggested: 6, accepted: 3, dismissed: 1, expired: 1, open_now: 1, outcomes: {} },
}
const impact: ImpactReport = {
  method: 'statistical', since: '2025-10-26T00:00:00Z', until: '2026-10-26T00:00:00Z',
  planting: { registered: 12, planted: 7, batches_registered: 1, plants_in_batches: 400, by_species: [{ name: 'Neem', count: 8 }] },
  survival: { alive: 11, dead: 1, rate: 91.7, by_species: [{ species: 'Neem', alive: 8, dead: 0, rate: 100 }, { species: 'Mango', alive: 3, dead: 1, rate: 75 }] },
  health: { assets_compared: 5, healthy_share_start: 40, healthy_share_end: 80 },
  growth: { comparable_assets: 0, median_height_change_pct: null },
  canopy: { trees_measured: 2, area_m2: 15.7 },
  coverage: { available: false, reason: 'Needs zone areas' },
}

beforeEach(() => {
  state.since = []
  state.analytics = analytics
  state.impact = impact
  state.csv.mockReset()
})

describe('analytics report', () => {
  it('shows the counted figures of each section and says it is statistical', () => {
    render(<AnalyticsPage />)
    expect(screen.getByRole('heading', { level: 1, name: 'Analytics' })).toBeInTheDocument()
    expect(screen.getByText(/statistical/i)).toBeInTheDocument()
    const tasks = screen.getByRole('region', { name: 'Tasks' })
    expect(within(tasks).getByText('75%')).toBeInTheDocument()
    expect(within(tasks).getByText('3 of 4 with a due date')).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: 'Opened by category' })).getAllByRole('listitem')[0]).toHaveTextContent(/pest.*3/i)
    expect(within(screen.getByRole('list', { name: 'Products used most' })).getByText('Neem oil')).toBeInTheDocument()
    expect(screen.getByText('6.5 days')).toBeInTheDocument()
  })

  it('asks for the chosen period (12 months by default)', async () => {
    render(<AnalyticsPage />)
    const first = state.since.at(-1)!
    expect(Math.abs(new Date(first).getTime() - new Date(monthsAgo(12)).getTime())).toBeLessThan(60_000)
    await userEvent.click(screen.getByRole('button', { name: '3 months' }))
    expect(screen.getByRole('button', { name: '3 months' })).toHaveAttribute('aria-pressed', 'true')
    const after = state.since.at(-1)!
    expect(Math.abs(new Date(after).getTime() - new Date(monthsAgo(3)).getTime())).toBeLessThan(60_000)
  })

  it('downloads every figure as CSV', async () => {
    render(<AnalyticsPage />)
    await userEvent.click(screen.getByRole('button', { name: 'Download CSV' }))
    const [name, csv] = state.csv.mock.calls[0] as [string, string]
    expect(name).toMatch(/^analytics-\d{4}-\d{2}-\d{2}-to-\d{4}-\d{2}-\d{2}\.csv$/)
    expect(csv.split(/\r?\n/)[0]).toBe('section,figure,value,note')
    expect(csv).toContain('Tasks,Done on time,75,3/4')
    expect(csv).toContain('Products used most,Neem oil,3')
  })

  it('cannot download while the report is loading', () => {
    state.analytics = undefined
    render(<AnalyticsPage />)
    expect(screen.getByRole('button', { name: 'Download CSV' })).toBeDisabled()
  })
})

describe('impact report', () => {
  it('shows planting, survival by species, health change and canopy', () => {
    render(<ImpactPage />)
    expect(screen.getByText('91.7%')).toBeInTheDocument()
    const rows = within(screen.getByRole('table')).getAllByRole('row')
    expect(rows[2]).toHaveTextContent(/Mango\s*3\s*1\s*75%/)
    expect(screen.getByText('40% → 80%')).toBeInTheDocument()
    expect(screen.getByText('15.7 m²')).toBeInTheDocument()
    expect(screen.getByText(/latest width of 2 trees/)).toBeInTheDocument()
  })

  it('uses the singular for one tree', () => {
    state.impact = { ...impact, canopy: { trees_measured: 1, area_m2: 3.1 } }
    render(<ImpactPage />)
    expect(screen.getByText('from the latest width of 1 tree, assuming a round crown')).toBeInTheDocument()
  })

  it('shows a dash and the reason where a figure cannot be worked out', () => {
    render(<ImpactPage />)
    expect(screen.getByText(/needs two height measurements/i)).toBeInTheDocument()
    expect(screen.getByText(/needs zone areas/i)).toBeInTheDocument()
  })
})
