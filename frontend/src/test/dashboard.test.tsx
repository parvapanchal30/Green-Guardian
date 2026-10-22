import { render, screen } from '@testing-library/react'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Dashboard } from '../api/types'

const state = vi.hoisted(() => ({ dash: {} as Record<string, unknown> }))

vi.mock('../lib/slice', () => ({
  useDashboard: () => state.dash,
  useLocations: () => ({ data: { items: [{ id: 'l1', name: 'Zone 4' }] } }),
  useRecommendations: () => ({ data: { items: [], total: 0 } }),
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
  ],
}

function renderHome() {
  const ctx = {
    ws: 'w1', workspace: { id: 'w1', name: 'City Green Cover', mode: 'green_management', role: 'manager' }, capabilities: [],
  }
  return render(
    <MemoryRouter initialEntries={['/w/w1']}>
      <Routes>
        <Route path="/w/:ws" element={<Outlet context={ctx} />}>
          <Route index element={<HomePage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('dashboard states', () => {
  beforeEach(() => {
    state.dash = { isLoading: false, error: null, data: undefined, refetch: vi.fn() }
  })

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
    expect(screen.queryByText('Overdue tasks')).not.toBeInTheDocument()
  })

  it('says so when every registered asset has left the lifecycle, instead of claiming there are none', () => {
    state.dash = { ...state.dash, data: { ...data, assets: { total: 0, exited: 3, by_kind: {}, health: { healthy: 0, at_risk: 0, critical: 0, unknown: 0 } }, recent_activity: [] } }
    renderHome()
    expect(screen.getByText(/3 registered assets have left the lifecycle/)).toBeInTheDocument()
  })

  it('shows assets that left the lifecycle as their own figure, apart from the active ones', () => {
    state.dash = { ...state.dash, data: { ...data, assets: { ...data.assets, exited: 2 } } }
    renderHome()
    expect(screen.getByText('Left the lifecycle').nextElementSibling).toHaveTextContent('2')
    expect(screen.getByText('Assets').nextElementSibling).toHaveTextContent('5')
  })

  it('renders server-computed figures, KPI availability and activity', () => {
    state.dash = { ...state.dash, data }
    renderHome()
    expect(screen.getByText('Overdue tasks').nextElementSibling).toHaveTextContent('2')
    expect(screen.getByText('Inspections due').nextElementSibling).toHaveTextContent('2')
    expect(screen.getByText('No health data')).toBeInTheDocument()
    expect(screen.getByText('Needs planting and loss records')).toBeInTheDocument()
    expect(screen.getByText(/2 healthy of 4 assets/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'GG-001 Leaf yellowing' })).toHaveAttribute('href', '/w/w1/issues/i1')
  })
})
