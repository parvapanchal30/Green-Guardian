import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { activeItemId, menuFor, sectionTabs } from '../app/routes'

const state = vi.hoisted(() => ({ api: vi.fn() }))

vi.mock('../api/client', async (orig) => ({ ...(await orig<typeof import('../api/client')>()), api: state.api }))
vi.mock('../lib/auth', () => ({ useAuth: () => ({ status: 'authed', user: { id: 'u1', name: 'Asha (owner)', email: 'demo.owner@example.com' }, logout: vi.fn(() => Promise.resolve()) }) }))
vi.mock('../lib/queries', () => ({
  useWorkspace: () => ({ isLoading: false, error: null, data: { id: 'w1', name: 'Riverside Campus Green Cover', mode: 'green_management', role: 'owner' } }),
  useWorkspaces: () => ({ data: [{ id: 'w1', name: 'Riverside Campus Green Cover' }] }),
  useCapabilities: () => ({ data: [] }),
}))
vi.mock('../lib/slice', async (orig) => ({
  ...(await orig<typeof import('../lib/slice')>()),
  useDashboard: () => ({ data: { work: { open_tasks: 4, open_issues: 1, open_recommendations: 3 } } }),
}))

import { WorkspaceLayout } from '../app/WorkspaceLayout'

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/w/:ws/*" element={<WorkspaceLayout />}>
            <Route path="*" element={<p>page body</p>} />
          </Route>
          <Route path="/login" element={<p>signed out</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  state.api.mockReset()
  state.api.mockResolvedValue({ items: [], total: 0 })
})
afterEach(() => {
  document.documentElement.removeAttribute('data-theme')
  localStorage.clear()
})

describe('menu model', () => {
  const items = (mode: 'green_management' | 'agricultural_production', role: 'owner' | 'worker' = 'owner') => {
    const m = menuFor(mode, role)
    return [...m.sections.flatMap((s) => s.items), ...m.footer]
  }

  it('marks the most specific entry: Species on its page, Assets on a plant page, Coming next on a planned page', () => {
    const all = items('green_management')
    expect(activeItemId('assets/species', all)).toBe('species')
    expect(activeItemId('assets', all)).toBe('assets')
    expect(activeItemId('assets/trees', all)).toBe('assets')
    expect(activeItemId('assets/0193-abc', all)).toBe('assets')
    expect(activeItemId('', all)).toBe('today')
    expect(activeItemId('monitor/growth', all)).toBe('health')
    expect(activeItemId('reports/impact', all)).toBe('reports')
    expect(activeItemId('settings/audit', all)).toBe('settings')
    expect(activeItemId('ai/disease-detection', all)).toBe('coming')
    expect(activeItemId('ai/datasets/d1', all)).toBe('datasets')
  })

  it('lists only working pages, with Harvests for farms, and planned features only through Coming next', () => {
    const green = items('green_management').map((i) => i.id)
    const farm = items('agricultural_production').map((i) => i.id)
    expect(green).not.toContain('harvests')
    expect(farm).toContain('harvests')
    expect(green).toEqual(expect.arrayContaining(['today', 'assets', 'species', 'zones', 'tasks', 'issues', 'inspections', 'health', 'map', 'weather', 'agent', 'reports', 'datasets', 'protocols', 'coming', 'settings']))
    expect(green).toHaveLength(16)
  })

  it('shows sibling pages as tabs, per mode and role, and none on detail pages', () => {
    expect(sectionTabs('assets/trees', 'green_management')?.map((r) => r.path)).toEqual(['assets', 'assets/trees', 'assets/plants'])
    expect(sectionTabs('assets', 'agricultural_production')?.map((r) => r.path)).toEqual(['assets', 'assets/plants', 'assets/batches', 'assets/crops'])
    expect(sectionTabs('assets/0193-abc', 'green_management')).toBeNull()
    expect(sectionTabs('settings/members', 'green_management', 'owner')?.map((r) => r.path)).toEqual(['settings/members', 'settings/audit'])
    expect(sectionTabs('settings/members', 'green_management', 'worker')).toBeNull() // the audit log is for managers
  })
})

describe('workspace frame', () => {
  it('marks only Species as current on the species page and shows open counts', () => {
    renderAt('/w/w1/assets/species')
    const nav = screen.getByRole('complementary', { name: 'Primary' })
    expect(within(nav).getByRole('link', { name: /Species/ })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByRole('link', { name: /^Assets/ })).not.toHaveAttribute('aria-current')
    expect(within(nav).getByRole('link', { name: /Tasks/ })).toHaveTextContent('4')
    expect(within(nav).getByRole('link', { name: /Operations agent/ })).toHaveTextContent('3')
    expect(within(nav).queryByText(/Disease Detection/)).not.toBeInTheDocument()
    expect(within(nav).getByRole('link', { name: /Coming next/ })).toHaveAttribute('href', '/w/w1/coming-next')
  })

  it('shows Trees and Plants as tabs on the assets pages', () => {
    renderAt('/w/w1/assets/trees')
    const tabs = screen.getByRole('navigation', { name: 'Pages in this section' })
    expect(within(tabs).getAllByRole('link').map((a) => a.textContent)).toEqual(['All assets', 'Trees', 'Plants'])
    expect(within(tabs).getByRole('link', { name: 'Trees' })).toHaveAttribute('aria-current', 'page')
  })

  it('More on the phone bar opens the menu and Esc closes it', async () => {
    renderAt('/w/w1')
    const more = within(screen.getByRole('navigation', { name: 'Main' })).getByRole('button', { name: 'More' })
    await userEvent.click(more)
    expect(more).toHaveAttribute('aria-expanded', 'true')
    await userEvent.keyboard('{Escape}')
    expect(more).toHaveAttribute('aria-expanded', 'false')
  })

  it('the account menu switches to dark and remembers it', async () => {
    renderAt('/w/w1')
    await userEvent.click(screen.getByRole('button', { name: /Account: Asha/ }))
    await userEvent.click(within(screen.getByRole('group', { name: 'Appearance' })).getByRole('button', { name: 'Dark' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(localStorage.getItem('gg.theme')).toBe('dark')
    await userEvent.click(within(screen.getByRole('group', { name: 'Appearance' })).getByRole('button', { name: 'Device' }))
    expect(document.documentElement).not.toHaveAttribute('data-theme')
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument()
  })

  it('search finds plants, issues and tasks by name or key, in this workspace', async () => {
    state.api.mockImplementation((url: string) => {
      if (url.startsWith('/workspaces/w1/assets')) return Promise.resolve({ items: [{ id: 'a1', label: 'Neem #102', tag_code: 'N-102', species_name: 'Neem', location_name: 'North avenue' }], total: 1 })
      if (url.startsWith('/workspaces/w1/issues')) return Promise.resolve({ items: [{ id: 'i1', key: 'GG-001', title: 'Neem #102 crown dieback' }], total: 1 })
      return Promise.resolve({ items: [{ id: 't1', key: 'T-001', title: 'Inspect Neem #102', issue_id: 'i1', asset_id: 'a1', asset_label: 'Neem #102' }], total: 1 })
    })
    renderAt('/w/w1')
    const [box] = screen.getAllByRole('searchbox', { name: 'Search' })
    await userEvent.type(box, 'neem')
    const results = await screen.findByRole('region', { name: 'Search results' })
    await waitFor(() => expect(within(results).getByRole('link', { name: /Neem #102 crown dieback/ })).toHaveAttribute('href', '/w/w1/issues/i1'))
    expect(within(results).getByRole('link', { name: /N-102/ })).toHaveAttribute('href', '/w/w1/assets/a1')
    expect(within(results).getByRole('link', { name: /T-001/ })).toHaveAttribute('href', '/w/w1/issues/i1') // a task opens its issue
    expect(state.api.mock.calls.map((c) => c[0])).toEqual(expect.arrayContaining(['/workspaces/w1/assets?q=neem&limit=5']))
  })

  it('search asks for two letters before it queries anything', async () => {
    renderAt('/w/w1')
    const [box] = screen.getAllByRole('searchbox', { name: 'Search' })
    await userEvent.type(box, 'n')
    await new Promise((r) => setTimeout(r, 400)) // past the 250 ms typing pause
    expect(screen.getByText(/at least 2 letters/)).toBeInTheDocument()
    expect(state.api).not.toHaveBeenCalled()
  })

  it('Record on the phone bar finds a plant and opens its observation form', async () => {
    state.api.mockResolvedValue({ items: [{ id: 'a1', label: 'Neem #102', tag_code: 'N-102', species_name: 'Neem', location_name: 'North avenue' }], total: 1 })
    renderAt('/w/w1')
    const bar = screen.getByRole('navigation', { name: 'Main' })
    await userEvent.click(within(bar).getByRole('button', { name: 'Record' }))
    const dialog = screen.getByRole('dialog', { name: 'Record for which plant?' })
    await userEvent.type(within(dialog).getByRole('searchbox'), 'N-10')
    expect(await within(dialog).findByRole('link', { name: /Neem #102/ })).toHaveAttribute('href', '/w/w1/assets/a1#record')
    expect(state.api.mock.calls.every((c) => String(c[0]).startsWith('/workspaces/w1/assets'))).toBe(true) // plants only
  })
})
