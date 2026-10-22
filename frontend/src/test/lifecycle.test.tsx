import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Asset, AssetLifecycle, LifecycleTemplate, StageChoice } from '../api/types'

const state = vi.hoisted(() => ({
  lifecycle: {} as Record<string, unknown>,
  template: {} as Record<string, unknown>,
  record: vi.fn(),
  recordState: { isPending: false, error: null as unknown },
}))

vi.mock('../lib/lifecycle', async (orig) => ({
  ...(await orig<typeof import('../lib/lifecycle')>()),
  useLifecycle: () => state.lifecycle,
  useLifecycleTemplate: () => state.template,
  useRecordStage: () => ({ mutate: state.record, ...state.recordState }),
}))

import { LifecyclePanel } from '../components/LifecyclePanel'
import { I18nProvider } from '../i18n'
import { enteredAt } from '../lib/lifecycle'

const choice = (key: string, label: string, kind: 'stage' | 'exit' = 'stage', manager_only = false): StageChoice => ({ key, label, kind, manager_only })
const asset = { id: 'a1', tracking_mode: 'individual', current_stage: 'planted', is_active: true } as Asset
const lc = (over: Partial<AssetLifecycle> = {}): AssetLifecycle => ({
  asset_id: 'a1', current_stage: 'planted', is_active: true,
  next_choices: [choice('growing', 'Growing'), choice('mature', 'Mature'), choice('dead', 'Dead', 'exit'), choice('removed', 'Removed', 'exit', true)],
  history: [{ id: 'e1', asset_id: 'a1', stage: 'planted', stage_label: 'Planted', previous_stage: null, entered_at: '2026-10-01T10:00:00Z', recorded_at: '2026-10-01T10:00:00Z', source: 'manual', correction: false, note: null, actor_id: 'u1' }],
  ...over,
})
const template: LifecycleTemplate = {
  mode: 'green_management',
  stages: [choice('planted', 'Planted'), choice('growing', 'Growing'), choice('mature', 'Mature')],
  exits_individual: [choice('dead', 'Dead', 'exit'), choice('removed', 'Removed', 'exit', true)],
  exits_population: [choice('failed', 'Failed (batch lost)', 'exit')],
  rules: [],
}

beforeEach(() => {
  state.lifecycle = { isLoading: false, error: null, data: lc(), refetch: vi.fn() }
  state.template = { data: template, isLoading: false }
  state.record.mockReset()
  state.recordState = { isPending: false, error: null }
})

const stageSelect = () => screen.getByLabelText(/new stage|correct the stage to/i)

describe('lifecycle panel', () => {
  it('shows the current stage and the append-only history', () => {
    render(<LifecyclePanel ws="w1" asset={asset} role="worker" />)
    expect(screen.getByRole('heading', { name: /lifecycle/i })).toHaveTextContent('Planted')
    expect(within(screen.getByRole('list', { name: 'Lifecycle history' })).getByText('Planted')).toBeInTheDocument()
    expect(screen.getByText(/nothing is edited or deleted/i)).toBeInTheDocument()
  })

  it('offers exactly the stages the server listed, and disables manager-only exits for a worker', () => {
    render(<LifecyclePanel ws="w1" asset={asset} role="worker" />)
    const options = within(stageSelect()).getAllByRole('option').map((o) => [o.textContent, (o as HTMLOptionElement).disabled])
    expect(options).toEqual([
      ['Choose…', false], ['Growing', false], ['Mature', false], ['Dead (ends the lifecycle)', false], ['Removed (ends the lifecycle) (manager)', true],
    ])
    expect(screen.queryByLabelText(/this is a correction/i)).not.toBeInTheDocument()
  })

  it('submits the chosen stage, date and note, and clears the form', async () => {
    state.record.mockImplementation((_b, opts) => opts?.onSuccess?.())
    render(<LifecyclePanel ws="w1" asset={asset} role="worker" />)
    await userEvent.selectOptions(stageSelect(), 'growing')
    await userEvent.type(screen.getByLabelText(/note/i), 'first leaves')
    await userEvent.click(screen.getByRole('button', { name: 'Record' }))
    expect(state.record).toHaveBeenCalledWith({ stage: 'growing', correction: false, entered_at: undefined, note: 'first leaves' }, expect.anything())
  })

  it('does not submit without a stage', async () => {
    render(<LifecyclePanel ws="w1" asset={asset} role="worker" />)
    await userEvent.click(screen.getByRole('button', { name: 'Record' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a stage.')
    expect(state.record).not.toHaveBeenCalled()
  })

  it('shows the server refusal verbatim', () => {
    state.recordState = { isPending: false, error: new Error('Cannot move from mature back to growing') }
    render(<LifecyclePanel ws="w1" asset={asset} role="worker" />)
    expect(screen.getByRole('alert')).toHaveTextContent('Cannot move from mature back to growing')
  })

  it('a viewer sees the history but no form', () => {
    render(<LifecyclePanel ws="w1" asset={asset} role="viewer" />)
    expect(screen.queryByRole('form', { name: /record a stage change/i })).not.toBeInTheDocument()
    expect(screen.getByText(/only workers and managers/i)).toBeInTheDocument()
  })

  it('an exited asset gives a worker no form and tells them a manager can reinstate it', () => {
    state.lifecycle = { isLoading: false, error: null, refetch: vi.fn(), data: lc({ current_stage: 'dead', is_active: false, next_choices: [] }) }
    render(<LifecyclePanel ws="w1" asset={{ ...asset, current_stage: 'dead', is_active: false }} role="worker" />)
    expect(screen.getByText(/left the lifecycle/i)).toBeInTheDocument()
    expect(screen.getByText(/a manager can reinstate/i)).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: /record a stage change/i })).not.toBeInTheDocument()
  })

  it('a manager can record a correction, which needs a written reason on the client too', async () => {
    state.lifecycle = { isLoading: false, error: null, refetch: vi.fn(), data: lc({ current_stage: 'mature', next_choices: [choice('dead', 'Dead', 'exit')] }) }
    render(<LifecyclePanel ws="w1" asset={{ ...asset, current_stage: 'mature' }} role="manager" />)
    await userEvent.click(screen.getByLabelText(/this is a correction/i))
    const options = within(stageSelect()).getAllByRole('option').map((o) => o.textContent)
    expect(options).toContain('Growing')
    expect(options).toContain('Planted')
    expect(options).not.toContain('Mature') // the current stage cannot be "corrected" to itself
    await userEvent.selectOptions(stageSelect(), 'growing')
    await userEvent.type(screen.getByLabelText(/reason \(required\)/i), 'short')
    await userEvent.click(screen.getByRole('button', { name: 'Record' }))
    expect(screen.getByRole('alert')).toHaveTextContent(/at least 10 characters/)
    expect(state.record).not.toHaveBeenCalled()
    await userEvent.type(screen.getByLabelText(/reason \(required\)/i), ' entered mature by mistake')
    await userEvent.click(screen.getByRole('button', { name: 'Record' }))
    expect(state.record).toHaveBeenCalledWith(expect.objectContaining({ stage: 'growing', correction: true, note: 'short entered mature by mistake' }), expect.anything())
  })

  it('uses the population exits when reinstating or correcting a batch', async () => {
    const batch = { ...asset, tracking_mode: 'population' } as Asset
    render(<LifecyclePanel ws="w1" asset={batch} role="manager" />)
    await userEvent.click(screen.getByLabelText(/this is a correction/i))
    const options = within(stageSelect()).getAllByRole('option').map((o) => o.textContent)
    expect(options).toContain('Failed (batch lost) (ends the lifecycle)')
    expect(options).not.toContain('Dead (ends the lifecycle)')
  })

  it('shows loading and error states', () => {
    state.lifecycle = { isLoading: true, error: null, data: undefined, refetch: vi.fn() }
    const { unmount } = render(<LifecyclePanel ws="w1" asset={asset} role="worker" />)
    expect(screen.getByText(/loading lifecycle/i)).toBeInTheDocument()
    unmount()
    state.lifecycle = { isLoading: false, error: new Error('boom'), data: undefined, refetch: vi.fn() }
    render(<LifecyclePanel ws="w1" asset={asset} role="worker" />)
    expect(screen.getByRole('button', { name: /retry|try again/i })).toBeInTheDocument()
  })
})

describe('lifecycle panel in Hindi', () => {
  it('translates the panel, the stages and the exit hints; history text from people stays as written', () => {
    render(<I18nProvider initial="hi"><LifecyclePanel ws="w1" asset={asset} role="worker" /></I18nProvider>)
    expect(screen.getByRole('heading', { name: /जीवन-चक्र/ })).toHaveTextContent('रोपित')
    const options = within(screen.getByLabelText('नया चरण')).getAllByRole('option').map((o) => o.textContent)
    expect(options).toEqual(['चुनें…', 'बढ़ रहा है', 'परिपक्व', 'मृत (जीवन-चक्र समाप्त करता है)', 'हटाया गया (जीवन-चक्र समाप्त करता है) (प्रबंधक)'])
    expect(screen.getByRole('button', { name: 'दर्ज करें' })).toBeInTheDocument()
  })
})

describe('enteredAt', () => {
  it('treats empty and today as "now" (a later time today would be rejected as the future) and other dates as noon UTC', () => {
    const today = new Date(2026, 9, 22, 8, 30)
    expect(enteredAt('', today)).toBeUndefined()
    expect(enteredAt('2026-10-22', today)).toBeUndefined()
    expect(enteredAt('2026-10-01', today)).toBe('2026-10-01T12:00:00Z')
  })
})
