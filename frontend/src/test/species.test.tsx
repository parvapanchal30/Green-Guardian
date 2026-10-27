import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { SpeciesItem } from '../api/types'

const state = vi.hoisted(() => ({ urls: [] as string[], items: [] as unknown[], role: 'manager', create: vi.fn() }))

vi.mock('../api/client', async (orig) => ({
  ...(await orig<typeof import('../api/client')>()),
  api: (url: string) => {
    state.urls.push(url)
    return Promise.resolve({ items: state.items, total: state.items.length, limit: 200, offset: 0 })
  },
}))
vi.mock('../lib/slice', async (orig) => ({
  ...(await orig<typeof import('../lib/slice')>()),
  useCreateSpecies: () => ({ mutate: state.create, isPending: false, error: null }),
}))
vi.mock('../app/WorkspaceLayout', () => ({
  useWorkspaceCtx: () => ({ ws: 'w1', workspace: { id: 'w1', mode: 'agricultural_production', role: state.role }, capabilities: [] }),
}))

import { SpeciesPage } from '../pages/SpeciesPage'

const sp = (over: Partial<SpeciesItem>): SpeciesItem => ({
  id: 's1', category: 'crop', common_name: 'Tomato', scientific_name: 'Solanum lycopersicum', is_global: true, assets: 2, plants: 2000, ...over,
})

function renderPage(crops = false) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter><SpeciesPage crops={crops} /></MemoryRouter></QueryClientProvider>)
}

beforeEach(() => {
  state.urls = []
  state.role = 'manager'
  state.create.mockReset()
  state.items = [sp({}), sp({ id: 's2', common_name: 'Field bean', is_global: false, assets: 0, plants: null, category: 'crop' })]
})

describe('species and crops', () => {
  it('Crops asks for crop species in use here and shows batches and plants', async () => {
    renderPage(true)
    const row = (await screen.findByText('Tomato')).closest('tr') as HTMLElement
    expect(within(row).getByRole('link', { name: '2' })).toHaveAttribute('href', '/w/w1/assets?species=s1')
    expect(row).toHaveTextContent('2,000')
    expect(state.urls[0]).toContain('category=crop')
    expect(state.urls[0]).toContain('mine=true')
    expect(screen.getByRole('heading', { name: 'Crops' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Category')).not.toBeInTheDocument()
  })

  it('Species shows this workspace\'s species, or the shared catalog on request, and marks its own entries', async () => {
    renderPage()
    const own = (await screen.findByText('Field bean')).closest('tr') as HTMLElement
    expect(own).toHaveTextContent('This workspace')
    expect(within(own).queryByRole('link')).not.toBeInTheDocument() // nothing to open when unused
    expect(state.urls[0]).toContain('mine=true') // this workspace's species by default (ADR-078)
    await userEvent.click(screen.getByRole('button', { name: 'Shared catalog' }))
    expect(state.urls.at(-1)).not.toContain('mine')
    expect(screen.getByText(/Species added in other workspaces are never shown/)).toBeInTheDocument()
  })

  it('a manager adds a species; a worker cannot', async () => {
    renderPage()
    await userEvent.click(screen.getByRole('button', { name: 'Add a species' }))
    const form = screen.getByRole('form', { name: 'Add a species' })
    await userEvent.type(within(form).getByLabelText('Name'), 'Jamun')
    await userEvent.selectOptions(within(form).getByLabelText('Category'), 'tree')
    await userEvent.click(within(form).getByRole('button', { name: 'Save the species' }))
    expect(state.create).toHaveBeenCalledWith({ category: 'tree', common_name: 'Jamun', scientific_name: undefined }, expect.anything())
  })

  it('a worker sees the catalog but cannot add to it', async () => {
    state.role = 'worker'
    renderPage()
    await screen.findByText('Tomato')
    expect(screen.queryByRole('button', { name: 'Add a species' })).not.toBeInTheDocument()
  })
})
