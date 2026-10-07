import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { MapFeature, MapFeatureCollection } from '../api/types'

const state = vi.hoisted(() => ({ q: {} as Record<string, unknown>, lastParams: undefined as unknown }))

vi.mock('../lib/slice', () => ({
  useMapLayer: (_ws: string, _layer: string, params: unknown) => { state.lastParams = params; return state.q },
  useMapLayers: () => ({
    data: [
      { key: 'assets', label: 'Biological assets', description: '', available: true, stage: 'mvp', geometry: 'point', requires: null },
      { key: 'disease_hotspots', label: 'Disease hotspots', description: '', available: false, stage: 'v2', geometry: 'polygon', requires: 'Disease detection' },
    ],
  }),
  useLocations: () => ({ data: { items: [{ id: 'l1', name: 'Zone 4' }] } }),
}))
// Leaflet needs a real layout engine; the map itself is exercised in the browser. Here it is a stand-in that exposes selection.
vi.mock('../components/AssetMap', () => ({
  AssetMap: ({ features, onSelect }: { features: MapFeature[]; onSelect: (id: string) => void }) => (
    <div data-testid="map">{features.map((f) => <button key={f.id} onClick={() => onSelect(f.id)}>{`pin ${f.properties.label}`}</button>)}</div>
  ),
}))

import { MapPage } from '../pages/MapPage'

const feature = (id: string, label: string, over: Partial<MapFeature['properties']> = {}): MapFeature => ({
  type: 'Feature', id, geometry: { type: 'Point', coordinates: [72.87, 19.07] },
  properties: {
    asset_id: id, label, kind: 'tree', tracking_mode: 'individual', estimated_count: null, species: 'Neem', location_id: 'l1', location_name: 'Zone 4',
    health_band: 'critical', health_score: 22, open_issue_count: 1, open_task_count: 2, position_source: 'asset', ...over,
  },
})
const counts = { all: 2, healthy: 1, at_risk: 0, critical: 1, open_issues: 1, tasks: 1, unlocated: 0 }
const fc = (over: Partial<MapFeatureCollection> = {}): MapFeatureCollection => ({
  type: 'FeatureCollection', layer: 'assets', filter: 'all', features: [feature('a1', 'Neem #482')], counts, bbox: [72, 19, 73, 20], truncated: false, ...over,
})

function renderMap(url = '/w/w1/monitor/map') {
  const ctx = { ws: 'w1', workspace: { id: 'w1', name: 'City', mode: 'green_management', role: 'viewer' }, capabilities: [] }
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/w/:ws" element={<Outlet context={ctx} />}>
          <Route path="monitor/map" element={<MapPage />} />
          <Route path="assets/:assetId" element={<p>asset profile page</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('operational map page', () => {
  beforeEach(() => { state.q = { isLoading: false, error: null, data: undefined, refetch: vi.fn() } })

  it('shows loading and error states', () => {
    state.q = { ...state.q, isLoading: true }
    const { unmount } = renderMap()
    expect(screen.getByText(/loading map/i)).toBeInTheDocument()
    unmount()
    state.q = { ...state.q, isLoading: false, error: new Error('boom') }
    renderMap()
    expect(screen.getByRole('button', { name: /retry|try again/i })).toBeInTheDocument()
  })

  it('explains an empty workspace and the undrawable-assets case', () => {
    state.q = { ...state.q, data: fc({ features: [], bbox: null, counts: { ...counts, all: 0, unlocated: 0 } }) }
    const { unmount } = renderMap()
    expect(screen.getByText('No assets to show')).toBeInTheDocument()
    unmount()
    state.q = { ...state.q, data: fc({ features: [], bbox: null, counts: { ...counts, all: 0, unlocated: 3 } }) }
    renderMap()
    expect(screen.getByText('No asset has a location on the map yet')).toBeInTheDocument()
    expect(screen.getByText(/3 asset\(s\) exist but have no coordinates/)).toBeInTheDocument()
  })

  it('populated: chips carry server counts, selecting shows state and links to the real profile', async () => {
    state.q = { ...state.q, data: fc() }
    renderMap()
    expect(screen.getByRole('button', { name: /^Critical\s*1$/ })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: /^All\s*2$/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/select an asset on the map/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'pin Neem #482' }))
    expect(screen.getByText('1 open issue(s)')).toBeInTheDocument()
    expect(screen.getByText('2 open task(s)')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: 'Open asset profile' })
    expect(link).toHaveAttribute('href', '/w/w1/assets/a1')
    await userEvent.click(link)
    expect(screen.getByText('asset profile page')).toBeInTheDocument()
  })

  it('filters are sent to the server and kept in the URL', async () => {
    state.q = { ...state.q, data: fc() }
    renderMap('/w/w1/monitor/map?filter=critical&kind=tree')
    expect(state.lastParams).toEqual({ filter: 'critical', location_id: undefined, kind: 'tree' })
    expect(screen.getByRole('button', { name: /^Critical/ })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: /^Tasks/ }))
    expect(state.lastParams).toMatchObject({ filter: 'tasks', kind: 'tree' })
  })

  it('tells the user when a filter matches nothing, and lists planned layers as planned only', () => {
    state.q = { ...state.q, data: fc({ features: [], filter: 'healthy' }) }
    renderMap('/w/w1/monitor/map?filter=healthy')
    expect(screen.getByText(/no assets match this filter/i)).toBeInTheDocument()
    expect(screen.getByText('Disease hotspots')).toBeInTheDocument()
    expect(screen.getByText('Planned · V2')).toBeInTheDocument()
  })
})
