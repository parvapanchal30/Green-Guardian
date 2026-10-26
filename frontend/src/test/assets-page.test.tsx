import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Asset } from '../api/types'

const state = vi.hoisted(() => ({
  list: {} as Record<string, unknown>,
  params: [] as Record<string, unknown>[],
  create: vi.fn(),
}))

vi.mock('../lib/slice', () => ({
  useAssets: (_ws: string, params: Record<string, unknown>) => {
    state.params.push(params)
    return state.list
  },
  useSpecies: () => ({ data: { items: [] } }),
  useLocations: () => ({ data: { items: [] } }),
  useCreateAsset: () => ({ mutate: state.create, isPending: false, error: null }),
  useCreateLocation: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useEvidence: (_ws: string, params: { asset_id: string }) => ({ data: { items: params.asset_id === 'a1' ? [{ id: 'e1' }] : [] } }),
}))
vi.mock('../components/EvidenceGallery', () => ({ EvidenceImage: () => <img alt="latest photo" /> }))
vi.mock('../lib/lifecycle', () => ({
  useLifecycleTemplate: () => ({
    data: { mode: 'green_management', stages: [{ key: 'planted', label: 'Planted' }, { key: 'mature', label: 'Mature' }], exits_individual: [], exits_population: [], rules: [] },
  }),
}))

import { AssetsPage } from '../pages/AssetsPage'

const asset = (over: Partial<Asset>): Asset => ({
  id: 'a1', label: 'Neem #1', kind: 'tree', tracking_mode: 'individual', tag_code: null, estimated_count: null, current_stage: 'planted',
  is_active: true, species_id: null, species_name: null, location_id: null, location_name: null, latitude: null, longitude: null,
  planted_at: null, attributes: {}, notes: null, created_at: '2026-10-01T00:00:00Z', archived_at: null,
  state: { health_score: null, health_band: null, health_observed_at: null, last_observed_at: null, open_issue_count: 0, open_task_count: 0, last_resolved_at: null },
  ...over,
})

function renderPage(only?: 'tree' | 'plant' | 'crop_batch') {
  const ctx = { ws: 'w1', workspace: { id: 'w1', name: 'Campus', mode: 'green_management', role: 'worker' }, capabilities: [] }
  return render(
    <MemoryRouter initialEntries={['/w/w1/assets']}>
      <Routes>
        <Route path="/w/:ws" element={<Outlet context={ctx} />}>
          <Route path="assets" element={<AssetsPage only={only} />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  state.params = []
  state.create.mockReset()
  state.list = {
    isLoading: false, error: null, refetch: vi.fn(),
    data: { total: 2, limit: 25, offset: 0, items: [asset({ id: 'a1', label: 'Neem #1', current_stage: 'mature' }), asset({ id: 'a2', label: 'Old oak', current_stage: 'dead', is_active: false })] },
  }
})

describe('assets list and lifecycle', () => {
  it('shows the stage of every asset and marks the ones that left the lifecycle', () => {
    renderPage()
    const rows = screen.getAllByRole('row')
    expect(within(rows[1]).getByText('Mature')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Dead')).toBeInTheDocument()
    expect(within(rows[2]).getByText('(left)')).toBeInTheDocument()
  })

  it('lists active assets by default and lets people ask for the ones that left, or all', async () => {
    renderPage()
    expect(state.params.at(-1)).toMatchObject({ active: true })
    await userEvent.selectOptions(screen.getByLabelText('Filter by lifecycle'), 'exited')
    expect(state.params.at(-1)).toMatchObject({ active: false, offset: 0 })
    await userEvent.selectOptions(screen.getByLabelText('Filter by lifecycle'), 'all')
    expect(state.params.at(-1)!.active).toBeUndefined()
  })

  it('offers the workspace template as the starting stage and sends it only when it is not the default', async () => {
    renderPage()
    await userEvent.click(screen.getByRole('button', { name: 'Register asset' }))
    const select = screen.getByLabelText('Starting stage')
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual(['Planted', 'Mature'])
    await userEvent.type(screen.getByLabelText(/name \/ identifier/i), 'Teak #9')
    await userEvent.click(within(screen.getByRole('form', { name: 'Register asset' })).getByRole('button', { name: 'Register asset' }))
    expect(state.create.mock.calls[0][0]).not.toHaveProperty('stage')
    await userEvent.selectOptions(select, 'mature')
    await userEvent.click(within(screen.getByRole('form', { name: 'Register asset' })).getByRole('button', { name: 'Register asset' }))
    expect(state.create.mock.calls[1][0]).toMatchObject({ label: 'Teak #9', stage: 'mature' })
  })
})

describe('views of one kind', () => {
  it('Trees is the same register, fixed to trees: no kind filter, its own title, trees registered by default', async () => {
    renderPage('tree')
    expect(screen.getByRole('heading', { name: 'Trees' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Filter by type')).not.toBeInTheDocument()
    expect(state.params.every((p) => p.kind === 'tree')).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: 'Register asset' }))
    expect((screen.getByLabelText('Type') as HTMLSelectElement).value).toBe('tree')
  })

  it('Crop batches asks only for batches and says so when there are none', () => {
    state.list = { isLoading: false, error: null, refetch: vi.fn(), data: { total: 0, limit: 25, offset: 0, items: [] } }
    renderPage('crop_batch')
    expect(state.params.every((p) => p.kind === 'crop_batch')).toBe(true)
    expect(screen.getByText('No crop batches registered yet')).toBeInTheDocument()
  })
})

describe('one list pattern, photo cards only on the kind tabs (ADR-073)', () => {
  it('"All" is the ledger table; every cell carries its column name for the phone card', () => {
    renderPage()
    const table = screen.getByRole('table', { name: 'Assets' })
    expect(screen.queryByRole('img', { name: 'latest photo' })).not.toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'View' })).not.toBeInTheDocument()
    const cells = within(within(table).getAllByRole('row')[1]).getAllByRole('cell')
    expect(cells[0]).not.toHaveAttribute('data-label') // the name heads the card
    expect(cells[1]).toHaveAttribute('data-label', 'Health')
  })

  it('Trees shows photo cards with the latest photo, or says there is none; the table is one click away', async () => {
    renderPage('tree')
    const cards = within(screen.getByRole('list', { name: 'Trees' })).getAllByRole('listitem')
    expect(within(cards[0]).getByRole('img', { name: 'latest photo' })).toBeInTheDocument()
    expect(within(cards[0]).getByRole('link', { name: 'Neem #1' })).toHaveAttribute('href', '/w/w1/assets/a1')
    expect(cards[1]).toHaveTextContent('No photo yet')
    expect(cards[1]).toHaveTextContent('(left)')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Table' }))
    expect(screen.getByRole('table', { name: 'Trees' })).toBeInTheDocument()
  })
})
