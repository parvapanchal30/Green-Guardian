import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { HarvestOverview, HarvestRecord } from '../api/types'

const state = vi.hoisted(() => ({ params: [] as Record<string, unknown>[], data: null as unknown }))

vi.mock('../lib/harvests', async (orig) => ({
  ...(await orig<typeof import('../lib/harvests')>()),
  useHarvestOverview: (_ws: string, params: Record<string, unknown>) => {
    state.params.push(params)
    return { isLoading: false, error: null, data: state.data, refetch: vi.fn() }
  },
}))
vi.mock('../app/WorkspaceLayout', () => ({
  useWorkspaceCtx: () => ({ ws: 'w1', workspace: { id: 'w1', mode: 'agricultural_production', role: 'viewer' }, capabilities: [] }),
}))

import { toCsv } from '../lib/csv'
import { HarvestsPage } from '../pages/HarvestsPage'

const rec = (over: Partial<HarvestRecord> & { asset_label?: string }): HarvestRecord & { asset_label: string } => ({
  id: 'h1', asset_id: 'a1', asset_label: 'Okra block B', harvested_at: '2026-10-20T10:00:00Z', quantity: 60, unit: 'kg', grade: 'A',
  note: null, supersedes_id: null, superseded_by: null, effective: true, withdrawn: false, recorded_by: 'u1', recorded_at: '2026-10-20T10:00:00Z', ...over,
})
const overview: HarvestOverview = {
  since: '2025-10-25T00:00:00Z', until: '2026-10-25T00:00:00Z',
  totals: { by_unit: { kg: 545, t: 0.32, count: 40 }, mass_tonnes: 0.865, records: 6 },
  by_month: [
    { month: '2026-09', by_unit: { kg: 140 }, mass_tonnes: 0.14, records: 1 },
    { month: '2026-10', by_unit: { kg: 405, t: 0.32, count: 40 }, mass_tonnes: 0.725, records: 5 },
  ],
  by_asset: [
    { asset_id: 'a1', asset_label: 'Okra block B', by_unit: { kg: 545 }, mass_tonnes: 0.545, records: 4 },
    { asset_id: 'a2', asset_label: 'Tomato block A', by_unit: { t: 0.32, count: 40 }, mass_tonnes: 0.32, records: 2 },
  ],
  records: [rec({}), rec({ id: 'h2', asset_id: 'a2', asset_label: 'Tomato block A', quantity: 0.32, unit: 't', grade: null, supersedes_id: 'h0', note: 'Re-weighed' })],
  truncated: false,
}

beforeEach(() => {
  state.params = []
  state.data = overview
})

describe('harvests overview', () => {
  it('shows the weight, the totals per unit, months, crops and records', () => {
    render(<MemoryRouter><HarvestsPage /></MemoryRouter>)
    expect(screen.getByText('0.865 t')).toBeInTheDocument()
    expect(screen.getAllByText(/545 kg · 0.32 t · 40 pieces/)[0]).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: 'Weight per month' })).getAllByRole('listitem')).toHaveLength(2)
    const table = screen.getByRole('table', { name: 'Per crop' })
    expect(within(table).getByRole('link', { name: 'Okra block B' })).toHaveAttribute('href', '/w/w1/assets/a1')
    expect(screen.getByText('Re-weighed').closest('li')).toHaveTextContent('Correction')
  })

  it('changes the period and the crop', async () => {
    render(<MemoryRouter><HarvestsPage /></MemoryRouter>)
    const first = state.params[0]
    await userEvent.click(screen.getByRole('button', { name: '3 months' }))
    expect(state.params.at(-1)?.since).not.toBe(first.since)
    await userEvent.selectOptions(screen.getByLabelText('Crop'), 'a2')
    expect(state.params.at(-1)?.asset_id).toBe('a2')
  })

  it('says when there is nothing in the period', () => {
    state.data = { ...overview, totals: { by_unit: {}, mass_tonnes: 0, records: 0 }, by_month: [], by_asset: [], records: [] }
    render(<MemoryRouter><HarvestsPage /></MemoryRouter>)
    expect(screen.getByText('No harvests in this period')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Download CSV' })).not.toBeInTheDocument()
  })
})

describe('csv', () => {
  it('quotes what needs quoting and defuses spreadsheet formulas', () => {
    expect(toCsv(['a', 'b'], [['x, y', 'say "hi"'], [1, null], ['=SUM(A1)', '-5']])).toBe('a,b\r\n"x, y","say ""hi"""\r\n1,\r\n\'=SUM(A1),\'-5\r\n')
  })
})
