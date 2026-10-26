import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { dueGroup } from '../lib/summary'

/* Phase 5 lists (ADR-073): the Tasks default per role and its due groups, and the Issues scopes and order. */

const state = vi.hoisted(() => ({
  role: 'manager',
  taskParams: [] as Record<string, unknown>[],
  issueParams: [] as Record<string, unknown>[],
  tasks: [] as unknown[],
}))

vi.mock('../app/WorkspaceLayout', () => ({
  useWorkspaceCtx: () => ({ ws: 'w1', workspace: { id: 'w1', mode: 'green_management', role: state.role }, capabilities: [] }),
}))
vi.mock('../lib/auth', () => ({ useAuth: () => ({ user: { id: 'u1' } }) }))
vi.mock('../lib/queries', () => ({ useMembers: () => ({ data: [] }) }))
vi.mock('../lib/slice', () => ({
  useTasks: (_ws: string, params: Record<string, unknown>) => {
    state.taskParams.push(params)
    return { isLoading: false, error: null, data: { items: state.tasks, total: state.tasks.length, limit: 25, offset: 0 } }
  },
  useTransitionTask: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useIssues: (_ws: string, params: Record<string, unknown>) => {
    state.issueParams.push(params)
    return { isLoading: false, error: null, data: { items: [], total: 0, limit: 25, offset: 0 } }
  },
}))

import { IssuesPage } from '../pages/IssuesPage'
import { TasksPage } from '../pages/TasksPage'

const NOW = new Date(2026, 9, 26, 9, 0) // Mon 26 Oct 2026, 09:00 local
const at = (days: number, hour = 12) => new Date(2026, 9, 26 + days, hour).toISOString()
const task = (id: string, due: string | null, overdue = false) => ({
  id, key: id, type: 'inspect', title: `Task ${id}`, description: null, issue_id: null, issue_key: null, asset_id: null, asset_label: null,
  location_id: null, assignee_id: 'u1', priority: 'p2', status: 'todo', source: 'manual', due_at: due, started_at: null, completed_at: null,
  completion_notes: null, overdue, created_at: at(-3), updated_at: at(-3), version: 1,
})

beforeEach(() => {
  state.role = 'manager'
  state.taskParams = []
  state.issueParams = []
  state.tasks = []
})

describe('due groups', () => {
  it('sorts open work into overdue, today, this week, later and no date by local calendar day', () => {
    expect(dueGroup({ due_at: at(-1), overdue: true }, NOW)).toBe('overdue')
    expect(dueGroup({ due_at: at(0, 23), overdue: false }, NOW)).toBe('today')
    expect(dueGroup({ due_at: at(1, 0), overdue: false }, NOW)).toBe('week')
    expect(dueGroup({ due_at: at(7), overdue: false }, NOW)).toBe('week')
    expect(dueGroup({ due_at: at(8), overdue: false }, NOW)).toBe('later')
    expect(dueGroup({ due_at: null, overdue: false }, NOW)).toBe('none')
  })
})

describe('tasks', () => {
  it('managers land on all open work, grouped by when it is due, overdue first', () => {
    state.tasks = [task('T-1', null), task('T-2', at(-2), true), task('T-3', at(30))]
    render(<MemoryRouter><TasksPage /></MemoryRouter>)
    expect(screen.getByRole('button', { name: 'All open' })).toHaveAttribute('aria-pressed', 'true')
    expect(state.taskParams[0]).toMatchObject({ is_open: true })
    expect(state.taskParams[0]).not.toHaveProperty('assignee')
    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(headings).toEqual(['Overdue', 'Later', 'No due date'])
    const overdue = screen.getByRole('region', { name: 'Overdue' })
    expect(within(overdue).getByText('Task T-2')).toBeInTheDocument()
  })

  it('field workers land on their own work', async () => {
    state.role = 'worker'
    render(<MemoryRouter><TasksPage /></MemoryRouter>)
    expect(screen.getByRole('button', { name: 'My tasks' })).toHaveAttribute('aria-pressed', 'true')
    expect(state.taskParams[0]).toMatchObject({ assignee: 'me', is_open: true })
    await userEvent.click(screen.getByRole('button', { name: 'Done / cancelled' }))
    expect(state.taskParams.at(-1)).toMatchObject({ is_open: false })
  })
})

describe('issues', () => {
  it('opens on open issues not waiting for a check, most severe first', async () => {
    render(<MemoryRouter><IssuesPage /></MemoryRouter>)
    expect(state.issueParams[0]).toMatchObject({ is_open: true, waiting: false, sort: 'severity' })
    await userEvent.click(screen.getByRole('button', { name: 'Waiting for a check' }))
    expect(state.issueParams.at(-1)).toMatchObject({ is_open: true, waiting: true, offset: 0 })
    expect(screen.getByText('Nothing is waiting for a check')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'All' }))
    expect(state.issueParams.at(-1)).not.toHaveProperty('is_open')
    expect(state.issueParams.at(-1)).not.toHaveProperty('waiting')
    await userEvent.selectOptions(screen.getByLabelText('Order'), 'recent')
    expect(state.issueParams.at(-1)).toMatchObject({ sort: 'recent' })
  })
})
