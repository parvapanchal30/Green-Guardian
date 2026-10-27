import { render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

/* ADR-080: the issue page in Field Ledger: who and what at the top, the workflow as steps, details and history aside. */

const state = vi.hoisted(() => ({ role: 'manager' }))

const issue = {
  id: 'i1', key: 'GG-001', title: 'Neem #102 crown dieback', description: 'Progressive dieback.', category: 'disease', severity: 'high',
  workflow_key: 'plant_health', state: 'treatment', is_open: true, asset_id: 'a1', asset_label: 'Neem #102', location_id: null,
  assignee_id: 'u-r', reporter_id: 'u-a', source: 'manual', origin_observation_id: null, recommendation_id: null,
  opened_at: '2026-10-25T10:00:00Z', updated_at: '2026-10-26T10:00:00Z', resolved_at: null, resolution_outcome: null,
  resolution_notes: null, resolved_by: null, version: 3,
  history: [
    { from_state: null, to_state: 'open', actor_id: 'u-a', note: null, at: '2026-10-25T10:00:00Z' },
    { from_state: 'open', to_state: 'treatment', actor_id: 'u-a', note: 'copper spray agreed', at: '2026-10-26T10:00:00Z' },
  ],
  evidence: [], actions: [],
  tasks: [{ id: 't1', key: 'T-001', title: 'Inspect and sample the bark', status: 'todo', overdue: false, due_at: '2026-10-28T10:00:00Z', assignee_id: 'u-r' }],
  verification: { status: 'not_applicable' },
  allowed_transitions: ['investigating', 'monitoring', 'resolved', 'closed_wont_fix'],
}

vi.mock('../lib/slice', async (orig) => ({
  ...(await orig<typeof import('../lib/slice')>()),
  useIssue: () => ({ isLoading: false, error: null, data: issue }),
  useWorkflows: () => ({
    data: [{ key: 'plant_health', label: 'Plant health', states: ['open', 'investigating', 'treatment', 'monitoring', 'resolved', 'closed_wont_fix'], terminal: ['resolved', 'closed_wont_fix'] }],
  }),
}))
vi.mock('../lib/queries', async (orig) => ({
  ...(await orig<typeof import('../lib/queries')>()),
  useMembers: () => ({ data: [{ user_id: 'u-a', name: 'Asha', email: 'a@x', role: 'owner' }, { user_id: 'u-r', name: 'Ravi', email: 'r@x', role: 'worker' }] }),
}))
vi.mock('../components/EvidenceGallery', () => ({ EvidenceGallery: () => <p>photos</p> }))

import { IssueDetailPage } from '../pages/IssueDetailPage'

function renderPage() {
  const ctx = { ws: 'w1', workspace: { id: 'w1', name: 'Campus', mode: 'green_management', role: state.role }, capabilities: [] }
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={['/w/w1/issues/i1']}>
        <Routes>
          <Route path="/w/:ws" element={<Outlet context={ctx} />}>
            <Route path="issues/:issueId" element={<IssueDetailPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  state.role = 'manager'
})

describe('issue page', () => {
  it('leads with the key, severity, title, who opened it and the plant', () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 1, name: 'Neem #102 crown dieback' })).toBeInTheDocument()
    expect(screen.getAllByText('GG-001').length).toBeGreaterThan(0)
    expect(screen.getByText(/by Asha/)).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Neem #102' })[0]).toHaveAttribute('href', '/w/w1/assets/a1')
  })

  it('shows the workflow as numbered steps, marking only stages the issue passed through', () => {
    renderPage()
    const steps = within(screen.getByRole('list', { name: /Plant health/ })).getAllByRole('listitem')
    expect(steps.map((s) => s.textContent)).toEqual(['✓Open', '2Investigating', '3Treatment', '4Monitoring', '5Resolved'])
    expect(steps[2]).toHaveAttribute('aria-current', 'step')
  })

  it('names the people: the task assignee, the person behind each change, and the history newest first', () => {
    renderPage()
    expect(screen.getByText('Inspect and sample the bark').closest('li')).toHaveTextContent('Ravi')
    const history = within(screen.getByRole('region', { name: 'History' })).getAllByRole('listitem')
    expect(history[0]).toHaveTextContent('copper spray agreed')
    expect(history[0]).toHaveTextContent('Asha')
    const details = screen.getByRole('region', { name: 'Details' })
    expect(details).toHaveTextContent('Plant health')
    expect(details).toHaveTextContent('Ravi')
  })

  it('offers the moves to managers only', () => {
    const { unmount } = renderPage()
    expect(screen.getByRole('region', { name: 'Move this issue' })).toBeInTheDocument()
    unmount()
    state.role = 'worker'
    renderPage()
    expect(screen.queryByRole('region', { name: 'Move this issue' })).not.toBeInTheDocument()
    expect(screen.getByText(/Only a manager can move an issue/)).toBeInTheDocument()
  })
})
