import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Asset, InspectionSchedule, ScheduleDetail } from '../api/types'

const state = vi.hoisted(() => ({
  list: {} as Record<string, unknown>,
  detail: {} as Record<string, unknown>,
  create: vi.fn(),
  update: vi.fn(),
  generate: vi.fn(),
  generated: null as unknown,
}))

vi.mock('../lib/schedules', async (orig) => ({
  ...(await orig<typeof import('../lib/schedules')>()),
  useSchedules: () => state.list,
  useSchedule: () => state.detail,
  useCreateSchedule: () => ({ mutate: state.create, isPending: false, error: null }),
  useUpdateSchedule: () => ({ mutate: state.update, isPending: false, error: null }),
  useGenerateDue: () => ({ mutate: state.generate, isPending: false, error: null, data: state.generated }),
}))
vi.mock('../lib/queries', async (orig) => ({
  ...(await orig<typeof import('../lib/queries')>()),
  useMembers: () => ({ data: [{ user_id: 'u-w', name: 'Ravi', email: 'r@x', role: 'worker' }] }),
}))

import { SchedulePanel } from '../components/SchedulePanel'
import { I18nProvider } from '../i18n'
import { days } from '../lib/schedules'

const asset = { id: 'a1', label: 'Neem #5', is_active: true } as Asset
const sched = (over: Partial<InspectionSchedule> = {}): InspectionSchedule => ({
  id: 's1', asset_id: 'a1', asset_label: 'Neem #5', location_id: null, location_name: null, title: 'Inspect Neem #5',
  task_type: 'inspect', interval_days: 30, lead_days: 2, next_due_at: '2026-11-20T10:00:00Z', assignee_id: 'u-w', priority: 'p3',
  active: true, created_by: 'u-m', created_at: '2026-10-20T10:00:00Z', updated_at: '2026-10-20T10:00:00Z', version: 1, ...over,
})

beforeEach(() => {
  state.list = { isLoading: false, error: null, data: [sched(), sched({ id: 's2', title: 'Monitor canopy', task_type: 'monitor', active: false })], refetch: vi.fn() }
  state.detail = {
    isLoading: false,
    data: {
      ...sched(),
      occurrences: [
        { due_at: '2026-10-21T10:00:00Z', outcome: 'skipped_open_task', task_id: null, task_key: null, task_status: null, missed: 0, created_at: '2026-10-21T10:00:00Z' },
        { due_at: '2026-09-21T10:00:00Z', outcome: 'created', task_id: 't1', task_key: 'T-007', task_status: 'todo', missed: 2, created_at: '2026-09-21T10:00:00Z' },
      ],
    } as ScheduleDetail,
  }
  state.create.mockReset()
  state.update.mockReset()
  state.generate.mockReset()
  state.generated = null
})

describe('recurring inspections on the asset page', () => {
  it('lists each schedule with its rhythm, next date, lead time, assignee and state', () => {
    render(<SchedulePanel ws="w1" asset={asset} role="worker" />)
    const [active, paused] = screen.getAllByRole('listitem')
    for (const text of ['Inspect Neem #5', 'Active', 'every 30 days', 'Inspect', 'next due', 'task created 2 days ahead', 'for Ravi']) expect(active).toHaveTextContent(text)
    expect(paused).toHaveTextContent('Paused')
    expect(paused).not.toHaveTextContent('next due') // a paused schedule has no next date to show
    expect(screen.queryByRole('button', { name: 'Pause' })).not.toBeInTheDocument() // a worker sees, a manager decides
    expect(screen.queryByRole('button', { name: /set up/i })).not.toBeInTheDocument()
  })

  it('shows what each due date produced', async () => {
    render(<SchedulePanel ws="w1" asset={asset} role="worker" />)
    await userEvent.click(within(screen.getAllByRole('listitem')[0]).getByRole('button', { name: 'History' }))
    const history = screen.getByRole('list', { name: 'Schedule history' })
    expect(history).toHaveTextContent('skipped: the previous task is still open')
    expect(history).toHaveTextContent('T-007')
    expect(history).toHaveTextContent('2 earlier dates passed without a task')
  })

  it('a manager pauses, resumes and creates due tasks now', async () => {
    state.generated = { due: 1, created: 1, skipped_open_task: 0, skipped_inactive_asset: 0, task_keys: ['T-009'] }
    render(<SchedulePanel ws="w1" asset={asset} role="manager" />)
    await userEvent.click(screen.getByRole('button', { name: 'Pause' }))
    expect(state.update).toHaveBeenCalledWith({ id: 's1', active: false })
    await userEvent.click(screen.getByRole('button', { name: 'Resume' }))
    expect(state.update).toHaveBeenLastCalledWith({ id: 's2', active: true })
    await userEvent.click(screen.getByRole('button', { name: 'Create due tasks now' }))
    expect(state.generate).toHaveBeenCalled()
    expect(screen.getByRole('status')).toHaveTextContent('1 task created.')
  })

  it('sets up a schedule, refusing a lead time as long as the interval', async () => {
    state.list = { isLoading: false, error: null, data: [], refetch: vi.fn() }
    render(<SchedulePanel ws="w1" asset={asset} role="manager" />)
    expect(screen.getByText(/no recurring inspection/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Set up a recurring inspection' }))
    const form = screen.getByRole('form', { name: 'Set up a recurring inspection' })
    await userEvent.clear(within(form).getByLabelText('Every (days)'))
    await userEvent.type(within(form).getByLabelText('Every (days)'), '7')
    await userEvent.clear(within(form).getByLabelText(/create the task ahead/i))
    await userEvent.type(within(form).getByLabelText(/create the task ahead/i), '7')
    await userEvent.click(within(form).getByRole('button', { name: 'Save the schedule' }))
    expect(screen.getByRole('alert')).toHaveTextContent('shorter than the interval')
    expect(state.create).not.toHaveBeenCalled()
    await userEvent.clear(within(form).getByLabelText(/create the task ahead/i))
    await userEvent.type(within(form).getByLabelText(/create the task ahead/i), '1')
    await userEvent.selectOptions(within(form).getByLabelText('Kind of check'), 'monitor')
    await userEvent.selectOptions(within(form).getByLabelText('Assign to'), 'u-w')
    await userEvent.click(within(form).getByRole('button', { name: 'Save the schedule' }))
    expect(state.create).toHaveBeenCalledWith(
      { asset_id: 'a1', title: undefined, task_type: 'monitor', interval_days: 7, lead_days: 1, first_due_at: undefined, assignee_id: 'u-w', priority: 'p3' },
      expect.anything(),
    )
  })

  it('offers no new schedule for an asset that left the lifecycle', () => {
    render(<SchedulePanel ws="w1" asset={{ ...asset, is_active: false }} role="manager" />)
    expect(screen.queryByRole('button', { name: 'Set up a recurring inspection' })).not.toBeInTheDocument()
  })

  it('renders in Hindi', () => {
    render(<I18nProvider initial="hi"><SchedulePanel ws="w1" asset={asset} role="manager" /></I18nProvider>)
    expect(screen.getByRole('heading', { name: 'नियमित निरीक्षण' })).toBeInTheDocument()
    expect(screen.getAllByText('हर 30 दिन')).toHaveLength(2)
  })

  it('accepts only whole days in range', () => {
    expect(days('7', 365)).toBe(7)
    expect(days('0', 365)).toBeNull()
    expect(days('0', 30, 0)).toBe(0)
    expect(days('1.5', 365)).toBeNull()
    expect(days('400', 365)).toBeNull()
  })
})
