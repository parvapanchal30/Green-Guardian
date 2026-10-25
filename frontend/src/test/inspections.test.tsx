import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({ urls: [] as string[], tasks: [] as unknown[], schedules: [] as unknown[], update: vi.fn(), generate: vi.fn(), role: 'manager' }))

vi.mock('../api/client', async (orig) => ({
  ...(await orig<typeof import('../api/client')>()),
  api: (url: string) => {
    state.urls.push(url)
    return Promise.resolve({ items: state.tasks, total: state.tasks.length, limit: 100, offset: 0 })
  },
}))
vi.mock('../lib/schedules', async (orig) => ({
  ...(await orig<typeof import('../lib/schedules')>()),
  useSchedules: () => ({ isLoading: false, error: null, data: state.schedules }),
  useUpdateSchedule: () => ({ mutate: state.update, isPending: false, error: null }),
  useGenerateDue: () => ({ mutate: state.generate, isPending: false, error: null, data: undefined }),
}))
vi.mock('../lib/queries', async (orig) => ({
  ...(await orig<typeof import('../lib/queries')>()),
  useMembers: () => ({ data: [{ user_id: 'u-w', name: 'Ravi', email: 'r@x', role: 'worker' }] }),
}))
vi.mock('../app/WorkspaceLayout', () => ({
  useWorkspaceCtx: () => ({ ws: 'w1', workspace: { id: 'w1', mode: 'green_management', role: state.role }, capabilities: [] }),
}))

import { InspectionsPage } from '../pages/InspectionsPage'

function page() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter><InspectionsPage /></MemoryRouter></QueryClientProvider>)
}

beforeEach(() => {
  state.urls = []
  state.role = 'manager'
  state.update.mockReset()
  state.generate.mockReset()
  state.tasks = [{
    id: 't1', key: 'T-004', type: 'inspect', title: 'Monthly check of Banyan', status: 'todo', overdue: true, source: 'schedule',
    due_at: '2026-10-20T10:00:00Z', asset_id: 'a1', asset_label: 'Banyan #01', assignee_id: 'u-w',
  }]
  state.schedules = [
    { id: 's1', asset_id: 'a1', asset_label: 'Banyan #01', location_id: null, location_name: null, title: 'Monthly check of Banyan', interval_days: 30, next_due_at: '2026-11-26T10:00:00Z', assignee_id: 'u-w', active: true },
    { id: 's2', asset_id: null, asset_label: null, location_id: 'l1', location_name: 'North zone', title: 'Walk the north zone', interval_days: 7, next_due_at: '2026-10-30T10:00:00Z', assignee_id: null, active: false },
  ]
})

describe('inspections', () => {
  it('lists open inspection and monitoring tasks, marking the recurring ones', async () => {
    page()
    const row = (await screen.findByText('T-004')).closest('li') as HTMLElement
    for (const text of ['Monthly check of Banyan', 'Overdue', 'Recurring', 'Banyan #01', 'Ravi']) expect(row).toHaveTextContent(text)
    expect(state.urls[0]).toContain('type=inspect&type=monitor')
    expect(state.urls[0]).toContain('is_open=true')
  })

  it('lists every recurring inspection, of assets and of places, and a manager pauses or resumes them', async () => {
    page()
    const table = screen.getByRole('table', { name: 'Recurring inspections' })
    const [, banyan, zone] = within(table).getAllByRole('row')
    expect(within(banyan).getByRole('link', { name: 'Banyan #01' })).toHaveAttribute('href', '/w/w1/assets/a1')
    expect(banyan).toHaveTextContent('every 30 days')
    expect(within(zone).getByRole('link', { name: 'North zone' })).toHaveAttribute('href', '/w/w1/locations')
    expect(zone).toHaveTextContent('Paused')
    expect(zone).toHaveTextContent('Unassigned')
    await userEvent.click(within(zone).getByRole('button', { name: 'Resume' }))
    expect(state.update).toHaveBeenCalledWith({ id: 's2', active: true })
    await userEvent.click(screen.getByRole('button', { name: 'Create due tasks now' }))
    expect(state.generate).toHaveBeenCalled()
  })

  it('a worker sees everything but changes nothing', async () => {
    state.role = 'worker'
    page()
    await screen.findByText('T-004')
    expect(screen.queryByRole('button', { name: /pause|resume|create due/i })).not.toBeInTheDocument()
  })
})
