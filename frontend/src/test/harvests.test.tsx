import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Asset, AssetHarvests, HarvestRecord } from '../api/types'

const state = vi.hoisted(() => ({
  data: {} as Record<string, unknown>,
  record: vi.fn(),
  correct: vi.fn(),
  recordState: { isPending: false, error: null as unknown },
}))

vi.mock('../lib/harvests', async (orig) => ({
  ...(await orig<typeof import('../lib/harvests')>()),
  useHarvests: () => state.data,
  useRecordHarvest: () => ({ mutate: state.record, ...state.recordState }),
  useCorrectHarvest: () => ({ mutate: state.correct, isPending: false, error: null }),
}))

import { HarvestPanel } from '../components/HarvestPanel'

const asset = { id: 'a1', is_active: true } as Asset
const rec = (over: Partial<HarvestRecord>): HarvestRecord => ({
  id: 'h1', asset_id: 'a1', harvested_at: '2026-10-10T08:00:00Z', quantity: 120, unit: 'kg', grade: 'A', note: 'first picking',
  supersedes_id: null, superseded_by: null, effective: true, withdrawn: false, recorded_by: 'u1', recorded_at: '2026-10-10T09:00:00Z', ...over,
})
const harvests = (history: HarvestRecord[], by_unit: Record<string, number> = { kg: 120 }, mass = 0.12): AssetHarvests => ({
  asset_id: 'a1', totals: { by_unit, mass_tonnes: mass, records: history.filter((h) => h.effective && h.quantity > 0).length }, history,
})
const ok = (data: AssetHarvests) => ({ isLoading: false, error: null, data, refetch: vi.fn() })

beforeEach(() => {
  state.data = ok(harvests([rec({})]))
  state.record.mockReset()
  state.correct.mockReset()
  state.recordState = { isPending: false, error: null }
})

describe('harvest panel', () => {
  it('shows totals per unit and the history', () => {
    state.data = ok(harvests([rec({ id: 'h2', quantity: 40, unit: 'count', grade: null, note: null }), rec({})], { kg: 120, count: 40 }))
    render(<HarvestPanel ws="w1" asset={asset} role="worker" />)
    expect(screen.getByRole('heading', { name: /harvests/i })).toHaveTextContent('120 kg · 40 pieces')
    const items = within(screen.getByRole('list', { name: 'Harvest history' })).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[1]).toHaveTextContent('grade A')
  })

  it('says so when nothing has been harvested', () => {
    state.data = ok(harvests([], {}, 0))
    render(<HarvestPanel ws="w1" asset={asset} role="worker" />)
    expect(screen.getByText(/nothing has been harvested/i)).toBeInTheDocument()
  })

  it('records a harvest with the entered quantity, unit and grade', async () => {
    state.record.mockImplementation((_b, opts) => opts?.onSuccess?.())
    render(<HarvestPanel ws="w1" asset={asset} role="worker" />)
    await userEvent.type(screen.getByLabelText('Quantity'), '55.5')
    await userEvent.selectOptions(screen.getByLabelText('Unit'), 't')
    await userEvent.type(screen.getByLabelText(/grade/i), 'B')
    await userEvent.click(screen.getByRole('button', { name: 'Record harvest' }))
    expect(state.record).toHaveBeenCalledWith({ quantity: 55.5, unit: 't', harvested_at: undefined, grade: 'B', note: undefined }, expect.anything())
  })

  it('refuses an empty or non-positive quantity without calling the server', async () => {
    render(<HarvestPanel ws="w1" asset={asset} role="worker" />)
    await userEvent.click(screen.getByRole('button', { name: 'Record harvest' }))
    expect(screen.getByRole('alert')).toHaveTextContent(/greater than zero/i)
    await userEvent.type(screen.getByLabelText('Quantity'), '0')
    await userEvent.click(screen.getByRole('button', { name: 'Record harvest' }))
    expect(state.record).not.toHaveBeenCalled()
  })

  it('shows the server refusal verbatim', () => {
    state.recordState = { isPending: false, error: new Error('harvested_at cannot be in the future') }
    render(<HarvestPanel ws="w1" asset={asset} role="worker" />)
    expect(screen.getByRole('alert')).toHaveTextContent('harvested_at cannot be in the future')
  })

  it('a viewer sees the history and no form or correction buttons', () => {
    render(<HarvestPanel ws="w1" asset={asset} role="viewer" />)
    expect(screen.getByRole('list', { name: 'Harvest history' })).toBeInTheDocument()
    expect(screen.queryByRole('form')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Correct' })).not.toBeInTheDocument()
  })

  it('an asset that left the lifecycle takes no more harvests', () => {
    render(<HarvestPanel ws="w1" asset={{ ...asset, is_active: false } as Asset} role="manager" />)
    expect(screen.getByText(/left the lifecycle/i)).toBeInTheDocument()
    expect(screen.queryByRole('form')).not.toBeInTheDocument()
  })

  it('only a manager sees Correct, and a correction needs a reason of at least 10 characters', async () => {
    const { unmount } = render(<HarvestPanel ws="w1" asset={asset} role="worker" />)
    expect(screen.queryByRole('button', { name: 'Correct' })).not.toBeInTheDocument()
    unmount()
    render(<HarvestPanel ws="w1" asset={asset} role="manager" />)
    await userEvent.click(screen.getByRole('button', { name: 'Correct' }))
    expect(screen.getByRole('form', { name: 'Correct a harvest record' })).toBeInTheDocument()
    expect(screen.getByLabelText('Quantity')).toHaveValue(120)
    await userEvent.clear(screen.getByLabelText('Quantity'))
    await userEvent.type(screen.getByLabelText('Quantity'), '100')
    await userEvent.type(screen.getByLabelText(/reason for the correction/i), 'too short')
    await userEvent.click(screen.getByRole('button', { name: 'Save correction' }))
    expect(screen.getByRole('alert')).toHaveTextContent(/at least 10 characters/)
    expect(state.correct).not.toHaveBeenCalled()
    await userEvent.type(screen.getByLabelText(/reason for the correction/i), ' - weighed again')
    await userEvent.click(screen.getByRole('button', { name: 'Save correction' }))
    expect(state.correct).toHaveBeenCalledWith(expect.objectContaining({ id: 'h1', quantity: 100, unit: 'kg', note: 'too short - weighed again' }), expect.anything())
  })

  it('shows replaced and withdrawn records as such and offers no correction for them', () => {
    state.data = ok(harvests([
      rec({ id: 'h3', quantity: 0, supersedes_id: 'h2', withdrawn: true, note: 'duplicate entry' }),
      rec({ id: 'h2', effective: false, superseded_by: 'h3' }),
    ], {}, 0))
    render(<HarvestPanel ws="w1" asset={asset} role="manager" />)
    expect(screen.getByText('Withdrawn')).toBeInTheDocument()
    expect(screen.getByText('Replaced')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Correct' })).not.toBeInTheDocument()
  })

  it('shows loading and error states', () => {
    state.data = { isLoading: true, error: null, data: undefined, refetch: vi.fn() }
    const { unmount } = render(<HarvestPanel ws="w1" asset={asset} role="worker" />)
    expect(screen.getByText(/loading harvests/i)).toBeInTheDocument()
    unmount()
    state.data = { isLoading: false, error: new Error('boom'), data: undefined, refetch: vi.fn() }
    render(<HarvestPanel ws="w1" asset={asset} role="worker" />)
    expect(screen.getByRole('button', { name: /retry|try again/i })).toBeInTheDocument()
  })
})
