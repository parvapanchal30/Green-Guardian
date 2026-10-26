import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Dashboard, Recommendation } from '../api/types'
import { translate } from '../i18n'
import { dayKey, homeSummary } from '../lib/summary'

const state = vi.hoisted(() => ({ dash: {} as Record<string, unknown>, recs: [] as unknown[], tasks: [] as unknown[] }))

vi.mock('../lib/slice', async (orig) => ({
  ...(await orig<typeof import('../lib/slice')>()),
  useDashboard: () => state.dash,
  useLocations: () => ({ data: { items: [{ id: 'l1', name: 'Zone 4' }] } }),
  useRecommendations: () => ({ data: { items: state.recs, total: state.recs.length } }),
  useTasks: () => ({ isLoading: false, error: null, data: { items: state.tasks, total: state.tasks.length } }),
  useAcceptRecommendation: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useDismissRecommendation: () => ({ mutate: vi.fn(), isPending: false, error: null }),
}))

import { HomePage } from '../pages/HomePage'

const data: Dashboard = {
  mode: 'green_management',
  as_of: '2026-10-07T12:00:00Z',
  filters: { location_id: null, kind: null },
  assets: { total: 5, exited: 0, by_kind: { tree: 5 }, health: { healthy: 2, at_risk: 1, critical: 1, unknown: 1 } },
  work: {
    open_issues: 3, open_issues_by_severity: { critical: 0, high: 1, medium: 1, low: 1 }, open_tasks: 4, overdue_tasks: 2,
    tasks_due_next_7_days: 1, inspections_due: 2, inspection_interval_days: 21, open_recommendations: 1,
  },
  kpis: [
    { key: 'survival', label: 'Survival', available: false, value: null, unit: '%', basis: null, reason: 'Needs planting and loss records' },
    { key: 'health', label: 'Health', available: true, value: 50, unit: '%', basis: '2 healthy of 4 assets with a recorded health score', reason: null },
  ],
  recent_activity: [
    { at: '2026-10-07T11:00:00Z', type: 'issue', ref_id: 'i1', asset_id: 'a1', key: 'GG-001', title: 'GG-001 Leaf yellowing', detail: 'opened as open' },
    { at: '2026-10-06T09:00:00Z', type: 'observation', ref_id: 'o1', asset_id: 'a2', key: null, title: 'Observation: Neem #101', detail: 'health 81' },
  ],
}

const rec = (id: string, over: Partial<Recommendation> = {}): Recommendation =>
  ({
    id, asset_id: 'a1', title: `Suggestion ${id}`, severity: 'high', method: 'rule', rule_key: 'inspection_gap', rule_version: 1, status: 'open',
    created_at: '2026-10-07T10:00:00Z', explanation: 'Not looked at', evidence: {}, proposed_action: { create: 'task' }, outcome: null,
    outcome_detail: null, outcome_at: null, dismissed_reason: null, ...over,
  }) as unknown as Recommendation

function renderHome(role = 'manager') {
  const ctx = { ws: 'w1', workspace: { id: 'w1', name: 'City Green Cover', mode: 'green_management', role }, capabilities: [] }
  return render(
    <QueryClientProvider client={new QueryClient()}>
    <MemoryRouter initialEntries={['/w/w1']}>
      <Routes>
        <Route path="/w/:ws" element={<Outlet context={ctx} />}>
          <Route index element={<HomePage />} />
        </Route>
      </Routes>
    </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  state.dash = { isLoading: false, error: null, data: undefined, refetch: vi.fn() }
  state.recs = []
  state.tasks = []
})

describe('home states', () => {
  it('shows a loading state', () => {
    state.dash = { ...state.dash, isLoading: true }
    renderHome()
    expect(screen.getByText(/loading dashboard/i)).toBeInTheDocument()
  })

  it('shows an error state with retry', () => {
    state.dash = { ...state.dash, error: new Error('boom') }
    renderHome()
    expect(screen.getByRole('button', { name: /retry|try again/i })).toBeInTheDocument()
  })

  it('shows the empty state for a workspace with no assets', () => {
    state.dash = { ...state.dash, data: { ...data, assets: { total: 0, exited: 0, by_kind: {}, health: { healthy: 0, at_risk: 0, critical: 0, unknown: 0 } }, recent_activity: [] } }
    renderHome()
    expect(screen.getByText('No assets yet')).toBeInTheDocument()
    expect(screen.queryByText(/built from these figures/)).not.toBeInTheDocument()
  })

  it('says so when every registered asset has left the lifecycle, instead of claiming there are none', () => {
    state.dash = { ...state.dash, data: { ...data, assets: { total: 0, exited: 3, by_kind: {}, health: { healthy: 0, at_risk: 0, critical: 0, unknown: 0 } }, recent_activity: [] } }
    renderHome()
    expect(screen.getByText(/3 registered assets have left the lifecycle/)).toBeInTheDocument()
  })
})

describe('home', () => {
  it('puts the decisions first, shows three and links to the rest', () => {
    state.dash = { ...state.dash, data }
    state.recs = [rec('r1'), rec('r2', { rule_key: 'critical_health' }), rec('r3'), rec('r4')]
    renderHome()
    const decide = screen.getByRole('heading', { name: 'Needs your decision' })
    const figures = screen.getByRole('heading', { name: 'Figures' })
    expect(decide.compareDocumentPosition(figures) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getAllByRole('link', { name: /Suggestion r/ })).toHaveLength(3)
    expect(screen.getByRole('link', { name: '1 more suggestion' })).toHaveAttribute('href', '/w/w1/ai/agent')
    expect(screen.getByText('4 suggestions from the operations agent')).toBeInTheDocument()
  })

  it('says the state of the place in one rule-built sentence, then the figures', () => {
    state.dash = { ...state.dash, data }
    renderHome()
    expect(
      screen.getByText(
        '5 living plants: 2 healthy, 1 at risk and 1 critical. 1 has no health score yet. 4 tasks are open, 2 of them overdue; 3 issues are open. 2 plants have not been looked at for 21 days. 1 suggestion is waiting for your decision.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '2 Healthy, 1 At risk, 1 Critical, 1 No health data' })).toBeInTheDocument()
    expect(screen.getByText('2 overdue · 1 due in 7 days · 3 open issues')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()
    expect(screen.getByText(/2 healthy of 4 assets/)).toBeInTheDocument()
    expect(screen.getByText('Needs planting and loss records')).toBeInTheDocument() // unavailable KPIs say why
  })

  it('counts plants that left the lifecycle apart from the living ones', () => {
    state.dash = { ...state.dash, data: { ...data, assets: { ...data.assets, exited: 2 } } }
    renderHome()
    expect(screen.getByText('2 left the lifecycle (not counted)')).toBeInTheDocument()
  })

  it('groups activity by day and leads with the record key', () => {
    state.dash = { ...state.dash, data }
    renderHome()
    const activity = screen.getByRole('region', { name: 'Recent activity' })
    expect(within(activity).getByText('GG-001')).toBeInTheDocument()
    expect(within(activity).getByRole('link', { name: 'Leaf yellowing' })).toHaveAttribute('href', '/w/w1/issues/i1')
    expect(within(activity).getByRole('link', { name: 'Observation: Neem #101' })).toHaveAttribute('href', '/w/w1/assets/a2')
  })

  it('lists what is due next, linked to its issue or plant', () => {
    state.dash = { ...state.dash, data }
    state.tasks = [{ id: 't1', key: 'T-001', title: 'Inspect Neem #102', issue_id: 'i1', asset_id: 'a1', due_at: null }]
    renderHome()
    const due = screen.getByRole('region', { name: 'Due next' })
    expect(within(due).getByRole('link', { name: 'Inspect Neem #102' })).toHaveAttribute('href', '/w/w1/issues/i1')
    expect(within(due).getByText('no date')).toBeInTheDocument()
  })

  it('offers Record to people who can record, not to viewers', async () => {
    state.dash = { ...state.dash, data }
    const { unmount } = renderHome('viewer')
    expect(screen.queryByRole('button', { name: 'Record' })).not.toBeInTheDocument()
    unmount()
    renderHome('worker')
    await userEvent.click(screen.getByRole('button', { name: 'Record' }))
    expect(screen.getByRole('dialog', { name: 'Record for which plant?' })).toBeInTheDocument()
  })
})

describe('summary sentence', () => {
  it('is the same figures in Hindi', () => {
    const s = homeSummary(data, (k, p) => translate('hi', k, p))
    expect(s).toContain('5 जीवित पौधे')
    expect(s).not.toMatch(/[A-Za-z]{3,}/) // no English words left
  })

  it('omits what is zero and says none overdue', () => {
    const quiet: Dashboard = { ...data, assets: { ...data.assets, health: { healthy: 5, at_risk: 0, critical: 0, unknown: 0 } }, work: { ...data.work, overdue_tasks: 0, inspections_due: 0, open_recommendations: 0, open_tasks: 1, open_issues: 1 } }
    expect(homeSummary(quiet, (k, p) => translate('en', k, p))).toBe('5 living plants: 5 healthy, 0 at risk and 0 critical. 1 task is open, none overdue; 1 issue is open.')
  })

  it('groups by calendar day', () => {
    const now = new Date('2026-10-26T15:00:00')
    expect(dayKey('2026-10-26T01:00:00', now)).toBe('today')
    expect(dayKey('2026-10-25T23:00:00', now)).toBe('yesterday')
    expect(dayKey('2026-10-24T12:00:00', now)).not.toMatch(/today|yesterday/)
  })
})
