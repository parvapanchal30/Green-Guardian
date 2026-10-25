import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ActionRecord, Asset, IssueDetail, Verification, Workflow } from '../api/types'

const state = vi.hoisted(() => ({
  actions: {} as Record<string, unknown>,
  record: vi.fn(),
  correct: vi.fn(),
  issue: {} as Record<string, unknown>,
  move: vi.fn(),
  moveTask: vi.fn(),
  role: 'manager' as string,
}))

vi.mock('../lib/actions', async (orig) => ({
  ...(await orig<typeof import('../lib/actions')>()),
  useActions: () => state.actions,
  useRecordAction: () => ({ mutate: state.record, isPending: false, error: null }),
  useCorrectAction: () => ({ mutate: state.correct, isPending: false, error: null }),
}))
vi.mock('../lib/queries', async (orig) => ({
  ...(await orig<typeof import('../lib/queries')>()),
  useMembers: () => ({ data: [{ user_id: 'u-w', name: 'Asha', email: 'a@x', role: 'worker' }] }),
}))
vi.mock('../lib/slice', async (orig) => ({
  ...(await orig<typeof import('../lib/slice')>()),
  useIssues: () => ({ data: { items: [{ id: 'i1', key: 'ISS-1', title: 'Leaf spot' }], total: 1 } }),
  useIssue: () => state.issue,
  useWorkflows: () => ({ data: [workflow] }),
  useTransitionIssue: () => ({ mutate: state.move, isPending: false, error: null, reset: vi.fn() }),
  useCreateTask: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useTasks: () => ({ isLoading: false, error: null, data: { items: [task], total: 1 } }),
  useTransitionTask: () => ({ mutate: state.moveTask, isPending: false, error: null }),
}))
vi.mock('../lib/auth', () => ({ useAuth: () => ({ user: { id: 'u-w' } }) }))
vi.mock('../app/WorkspaceLayout', () => ({
  useWorkspaceCtx: () => ({ ws: 'w1', workspace: { id: 'w1', mode: 'green_management', role: state.role }, capabilities: [] }),
}))
vi.mock('../components/EvidenceGallery', () => ({ EvidenceGallery: () => null }))

import { ActionPanel } from '../components/ActionPanel'
import { VerificationCard } from '../components/VerificationCard'
import { I18nProvider } from '../i18n'
import { amount } from '../lib/actions'
import { IssueDetailPage } from '../pages/IssueDetailPage'
import { TasksPage } from '../pages/TasksPage'

const workflow: Workflow = {
  key: 'plant_health', label: 'Plant health', states: ['open', 'investigating', 'resolved', 'closed_wont_fix'], initial: 'open',
  terminal: ['resolved', 'closed_wont_fix'], transitions: { open: ['investigating', 'resolved', 'closed_wont_fix'] },
}
const asset = { id: 'a1', is_active: true } as Asset
const task = {
  id: 't1', key: 'TSK-1', type: 'treat', title: 'Spray', description: null, issue_id: 'i1', issue_key: 'ISS-1', asset_id: 'a1',
  asset_label: 'Neem #7', location_id: null, assignee_id: 'u-w', priority: 'p3', status: 'in_progress', source: 'issue', due_at: null,
  started_at: null, completed_at: null, completion_notes: null, overdue: false, created_at: '2026-10-20T10:00:00Z',
  updated_at: '2026-10-20T10:00:00Z', version: 1,
}
const rec = (over: Partial<ActionRecord> = {}): ActionRecord => ({
  id: 'r1', asset_id: 'a1', issue_id: 'i1', issue_key: 'ISS-1', task_id: null, task_key: null, kind: 'treat', product: 'Neem oil',
  quantity: 2, unit: 'l', performed_at: '2026-10-20T10:00:00Z', performed_by: 'u-w', note: 'whole canopy', follow_up_task_id: 't9',
  follow_up_task_key: 'TSK-9', supersedes_id: null, superseded_by: null, effective: true, withdrawn: false, recorded_by: 'u-w',
  recorded_at: '2026-10-20T10:00:00Z', ...over,
})
const verification = (over: Partial<Verification> = {}): Verification => ({
  status: 'awaiting_follow_up', method: 'rule', min_change: 5, actions: 1, last_action_at: '2026-10-20T10:00:00Z', baseline_score: 30,
  baseline_at: '2026-10-19T10:00:00Z', follow_up_score: null, follow_up_at: null, change: null, required_for_success: true, ...over,
})

beforeEach(() => {
  state.actions = { isLoading: false, error: null, data: { asset_id: 'a1', history: [rec()] }, refetch: vi.fn() }
  state.record.mockReset()
  state.correct.mockReset()
  state.move.mockReset()
  state.moveTask.mockReset()
  state.role = 'manager'
})

const panel = (role = 'worker') => render(<MemoryRouter><ActionPanel ws="w1" asset={asset} role={role as never} /></MemoryRouter>)

describe('work records on the asset page', () => {
  it('lists what was done, how much, with what, by whom, for which issue, and the scheduled check', () => {
    panel()
    const row = within(screen.getByRole('list', { name: 'Work history' })).getByRole('listitem')
    for (const text of ['Treatment', '2 litres', 'Neem oil', 'by Asha', 'whole canopy', 'check: TSK-9']) expect(row).toHaveTextContent(text)
    expect(within(row).getByRole('link', { name: 'ISS-1' })).toHaveAttribute('href', '/w/w1/issues/i1')
    expect(within(row).queryByRole('button', { name: 'Correct' })).not.toBeInTheDocument() // a worker records, a manager corrects
  })

  it('records work with an issue and a follow-up check, and refuses a quantity of zero', async () => {
    state.record.mockImplementation((_b, opts) => opts?.onSuccess?.())
    panel()
    await userEvent.selectOptions(screen.getByLabelText('What was done'), 'pest_control')
    await userEvent.type(screen.getByLabelText('Product (optional)'), 'Neem oil')
    await userEvent.type(screen.getByLabelText('Quantity (optional)'), '0')
    await userEvent.click(screen.getByRole('button', { name: 'Record the work' }))
    expect(screen.getByRole('alert')).toHaveTextContent('greater than 0')
    expect(state.record).not.toHaveBeenCalled()
    await userEvent.clear(screen.getByLabelText('Quantity (optional)'))
    await userEvent.type(screen.getByLabelText('Quantity (optional)'), '1.5')
    await userEvent.selectOptions(screen.getByLabelText('For an open issue (optional)'), 'i1')
    await userEvent.type(screen.getByLabelText('Check the result after (days)'), '7')
    await userEvent.click(screen.getByRole('button', { name: 'Record the work' }))
    expect(state.record).toHaveBeenCalledWith(
      { kind: 'pest_control', product: 'Neem oil', quantity: 1.5, unit: 'l', performed_at: undefined, note: undefined, issue_id: 'i1', follow_up_days: 7 },
      expect.anything(),
    )
  })

  it('a manager corrects or withdraws a record with a reason; the replaced record stays visible', async () => {
    state.actions = {
      isLoading: false, error: null, refetch: vi.fn(),
      data: { asset_id: 'a1', history: [rec({ id: 'r2', supersedes_id: 'r1', product: 'Copper', follow_up_task_key: null }), rec({ effective: false, superseded_by: 'r2' })] },
    }
    panel('manager')
    const rows = within(screen.getByRole('list', { name: 'Work history' })).getAllByRole('listitem')
    expect(rows[0]).toHaveTextContent('Correction')
    expect(rows[1]).toHaveTextContent('Replaced')
    expect(within(rows[1]).queryByRole('button', { name: 'Correct' })).not.toBeInTheDocument() // only the effective record
    await userEvent.click(within(rows[0]).getByRole('button', { name: 'Correct' }))
    const form = screen.getByRole('form', { name: 'Correct a work record' })
    await userEvent.type(within(form).getByLabelText(/reason for the correction/i), 'too short')
    await userEvent.click(within(form).getByRole('button', { name: 'Save the correction' }))
    expect(screen.getByRole('alert')).toHaveTextContent('at least 10 characters')
    await userEvent.type(within(form).getByLabelText(/reason for the correction/i), ' really')
    await userEvent.click(within(form).getByLabelText(/withdraw the record/i))
    await userEvent.click(within(form).getByRole('button', { name: 'Save the correction' }))
    expect(state.correct).toHaveBeenCalledWith(expect.objectContaining({ id: 'r2', note: 'too short really', withdrawn: true, product: 'Copper' }), expect.anything())
  })

  it('offers no form for an asset that left the lifecycle', () => {
    render(<MemoryRouter><ActionPanel ws="w1" asset={{ ...asset, is_active: false }} role="manager" /></MemoryRouter>)
    expect(screen.queryByRole('form')).not.toBeInTheDocument()
    expect(screen.getByText(/left the lifecycle/)).toBeInTheDocument()
  })

  it('quantity and unit go together or not at all', () => {
    expect(amount('', 'l')).toEqual({})
    expect(amount('2', 'kg')).toEqual({ quantity: 2, unit: 'kg' })
    expect(amount('-1', 'kg')).toBe('invalid')
    expect(amount('abc', 'kg')).toBe('invalid')
  })
})

describe('verification', () => {
  it('names the rule and its inputs, never a diagnosis', () => {
    render(<VerificationCard v={verification({ status: 'improved', follow_up_score: 52, follow_up_at: '2026-10-22T10:00:00Z', change: 22 })} />)
    expect(screen.getByRole('heading', { name: /did the work help/i })).toHaveTextContent('Improved')
    expect(screen.getByText('Rule')).toBeInTheDocument()
    expect(screen.getByText(/\+22 points/)).toBeInTheDocument()
    expect(screen.getByText(/not a diagnosis/)).toBeInTheDocument()
  })

  it('says when nothing has been checked yet, and is silent where it does not apply', () => {
    const { rerender } = render(<VerificationCard v={verification()} />)
    expect(screen.getByText('Awaiting a follow-up check')).toBeInTheDocument()
    expect(screen.getByText('Not checked yet')).toBeInTheDocument()
    rerender(<VerificationCard v={verification({ status: 'not_applicable', required_for_success: false })} />)
    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
  })

  it('renders in Hindi', () => {
    render(<I18nProvider initial="hi"><VerificationCard v={verification({ status: 'worse', follow_up_score: 20, follow_up_at: '2026-10-22T10:00:00Z', change: -10 })} /></I18nProvider>)
    expect(screen.getByText('स्थिति बिगड़ी')).toBeInTheDocument()
    expect(screen.getByText('नियम')).toBeInTheDocument()
  })
})

const issueDetail = (over: Partial<IssueDetail> = {}): IssueDetail => ({
  id: 'i1', key: 'ISS-1', title: 'Leaf spot', description: null, category: 'disease', severity: 'medium', workflow_key: 'plant_health',
  state: 'open', is_open: true, asset_id: 'a1', asset_label: 'Neem #7', location_id: null, assignee_id: null, reporter_id: null,
  source: 'manual', origin_observation_id: null, recommendation_id: null, opened_at: '2026-10-19T10:00:00Z', updated_at: '2026-10-19T10:00:00Z',
  resolved_at: null, resolution_outcome: null, resolution_notes: null, resolved_by: null, version: 1,
  history: [], evidence: [], tasks: [], actions: [rec()], verification: verification(), allowed_transitions: ['investigating', 'resolved', 'closed_wont_fix'],
  ...over,
} as IssueDetail)

describe('closing a plant issue as fixed', () => {
  const open = async () => {
    render(<MemoryRouter><IssueDetailPage /></MemoryRouter>)
    await userEvent.click(screen.getByRole('button', { name: /resolve/i }))
  }

  it('asks for a check after the work, and sends it with the resolution', async () => {
    state.issue = { isLoading: false, error: null, data: issueDetail(), refetch: vi.fn() }
    await open()
    expect(screen.getByText(/required to close as fixed or mitigated/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Give a health score or a note')
    expect(state.move).not.toHaveBeenCalled()
    await userEvent.type(screen.getByLabelText(/health score now/i), '70')
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(state.move).toHaveBeenCalledWith(
      expect.objectContaining({ to_state: 'resolved', resolution: expect.objectContaining({ outcome: 'fixed', follow_up: { health_score: 70, notes: undefined } }) }),
      expect.anything(),
    )
  })

  it('does not ask for one when the outcome claims no success', async () => {
    state.issue = { isLoading: false, error: null, data: issueDetail(), refetch: vi.fn() }
    await open()
    await userEvent.selectOptions(screen.getByLabelText('Outcome'), 'no_action_needed')
    expect(screen.queryByText(/required to close as fixed/)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(state.move).toHaveBeenCalledWith(expect.objectContaining({ resolution: expect.not.objectContaining({ follow_up: expect.anything() }) }), expect.anything())
  })

  it('shows the work done for the issue and the verification', () => {
    state.issue = { isLoading: false, error: null, data: issueDetail(), refetch: vi.fn() }
    render(<MemoryRouter><IssueDetailPage /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: 'Work done for this issue' })).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: 'Work history' })).getByText('Treatment')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /did the work help/i })).toBeInTheDocument()
  })
})

describe('completing a task', () => {
  it('records what was done, with the kind the task stands for preselected', async () => {
    state.role = 'worker'
    render(<MemoryRouter><TasksPage /></MemoryRouter>)
    await userEvent.click(screen.getByRole('button', { name: 'Complete' }))
    const form = screen.getByRole('form', { name: /TSK-1/ })
    expect((within(form).getByLabelText('What was done') as HTMLSelectElement).value).toBe('treat')
    await userEvent.type(within(form).getByLabelText('Product (optional)'), 'Copper fungicide')
    await userEvent.type(within(form).getByLabelText('Quantity (optional)'), '1.5')
    await userEvent.type(within(form).getByLabelText(/health score now/i), '45')
    await userEvent.click(within(form).getByRole('button', { name: /mark.*done/i }))
    expect(state.moveTask).toHaveBeenCalledWith(
      { id: 't1', body: expect.objectContaining({ to_status: 'done', action: { kind: 'treat', product: 'Copper fungicide', quantity: 1.5, unit: 'l' }, observation: { health_score: 45, notes: undefined } }) },
      expect.anything(),
    )
  })

  it('records no work when the kind is left as not recorded', async () => {
    state.role = 'worker'
    render(<MemoryRouter><TasksPage /></MemoryRouter>)
    await userEvent.click(screen.getByRole('button', { name: 'Complete' }))
    const form = screen.getByRole('form', { name: /TSK-1/ })
    await userEvent.selectOptions(within(form).getByLabelText('What was done'), '')
    await userEvent.click(within(form).getByRole('button', { name: /mark.*done/i }))
    expect(state.moveTask.mock.calls[0][0].body.action).toBeUndefined()
  })
})
