import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentRunRecord } from '../api/types'

const state = vi.hoisted(() => ({
  recs: {} as Record<string, unknown>,
  runs: {} as Record<string, unknown>,
  recParams: [] as Record<string, unknown>[],
  run: { mutate: vi.fn(), isPending: false, data: undefined, error: null } as Record<string, unknown>,
}))

vi.mock('../lib/slice', () => ({
  useAgentRules: () => ({ isLoading: false, data: [{ key: 'inspection_gap', version: 2, method: 'rule', description: 'No attention for too long.', parameters: { inspection_gap_days: 21 } }] }),
  useRecommendations: (_ws: string, params: Record<string, unknown>) => { state.recParams.push(params); return state.recs },
  useAgentRuns: () => state.runs,
  useRunAgent: () => state.run,
  useAcceptRecommendation: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useDismissRecommendation: () => ({ mutate: vi.fn(), isPending: false, error: null }),
}))

import { AgentPage } from '../pages/AgentPage'

const record = (over: Partial<AgentRunRecord> = {}): AgentRunRecord => ({
  id: 'run1', trigger: 'scheduled', status: 'succeeded', requested_by: null, worker_id: 'host:1', started_at: '2026-10-18T06:00:00Z',
  finished_at: '2026-10-18T06:00:02Z', duration_s: 2.1, evaluated_assets: 12, findings: 3, recommendations_created: 2,
  recommendations_expired: 1, rules: [], diagnostics: {}, error: null, ...over,
})

function show(role: 'manager' | 'viewer' = 'manager') {
  const ctx = { ws: 'w1', workspace: { id: 'w1', name: 'City', mode: 'green_management', role }, capabilities: [] }
  return render(
    <MemoryRouter initialEntries={['/w/w1/agent']}>
      <Routes>
        <Route path="/w/:ws" element={<Outlet context={ctx} />}>
          <Route path="agent" element={<AgentPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('agent page', () => {
  beforeEach(() => {
    state.recParams = []
    state.recs = { isLoading: false, error: null, data: { items: [], total: 0, limit: 25, offset: 0 }, refetch: vi.fn() }
    state.runs = { isLoading: false, error: null, data: { items: [], total: 0, limit: 10, offset: 0 }, refetch: vi.fn() }
    state.run = { mutate: vi.fn(), isPending: false, data: undefined, error: null }
  })

  it('states honestly what the agent is and that irrigation advice is forecast-based', () => {
    show()
    expect(screen.getByText(/does not use machine learning or a language model/)).toBeInTheDocument()
    expect(screen.getByText(/does not know how wet the soil is/)).toBeInTheDocument()
    expect(screen.getByText('version 2')).toBeInTheDocument()
  })

  it('lists scheduled and manual runs with their counts, and shows a failure with its reason', () => {
    state.runs = {
      ...state.runs,
      data: { total: 3, limit: 10, offset: 0, items: [
        record(),
        record({ id: 'run2', trigger: 'manual', recommendations_created: 0, recommendations_expired: 0 }),
        record({ id: 'run3', status: 'failed', error: 'OperationalError: connection refused', started_at: '2026-10-17T06:00:00Z' }),
      ] },
    }
    show()
    expect(screen.getAllByText('Scheduled')).toHaveLength(2)
    expect(screen.getByText('Manual')).toBeInTheDocument()
    expect(screen.getAllByText(/12 asset\(s\) checked · 2 new · 1 expired/)).toHaveLength(1)
    expect(screen.getByRole('alert')).toHaveTextContent('OperationalError: connection refused')
  })

  it('says what a run skipped so an empty result is not read as "all clear"', () => {
    state.runs = {
      ...state.runs,
      data: { total: 1, limit: 10, offset: 0, items: [record({ diagnostics: { skipped: { weather_unavailable: 2, water_stress_signs: 1 }, weather: { requested: true, unavailable: 2 } } })] },
    }
    show()
    expect(screen.getByText(/2 × weather unavailable/)).toBeInTheDocument()
    expect(screen.getByText(/1 × water stress signs/)).toBeInTheDocument()
    expect(screen.getByText(/weather unavailable for 2 location\(s\)/)).toBeInTheDocument()
  })

  it('switches the suggestion list between open, accepted, dismissed and expired', async () => {
    show()
    expect(state.recParams[state.recParams.length - 1]).toMatchObject({ status: 'open' })
    await userEvent.click(screen.getByRole('button', { name: 'Expired' }))
    expect(state.recParams[state.recParams.length - 1]).toMatchObject({ status: 'expired' })
    expect(screen.getByText('No expired suggestions')).toBeInTheDocument()
  })

  it('only offers "Run checks now" to people who can decide', () => {
    const { unmount } = show('manager')
    expect(screen.getByRole('button', { name: 'Run checks now' })).toBeInTheDocument()
    unmount()
    show('viewer')
    expect(screen.queryByRole('button', { name: 'Run checks now' })).not.toBeInTheDocument()
  })

  it('reports the result of a manual run including expired suggestions', () => {
    state.run = { ...state.run, data: { run: record(), evaluated_assets: 4, created: [{}], expired: 2, rules: [], note: '' } }
    show()
    expect(screen.getByRole('status')).toHaveTextContent('Checked 4 asset(s); 1 new and 2 expired suggestion(s).')
  })
})
