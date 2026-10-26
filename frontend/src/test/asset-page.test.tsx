import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Evidence } from '../api/types'

const state = vi.hoisted(() => ({
  photos: [] as unknown[],
  obs: [] as unknown[],
  timeline: [] as unknown[],
}))

const asset = {
  id: 'a1', label: 'Neem #102', kind: 'tree', tracking_mode: 'individual', tag_code: 'N-102', estimated_count: null, current_stage: 'mature',
  is_active: true, species_id: 's1', species_name: 'Neem', location_id: 'l1', location_name: 'North avenue', latitude: 19.1352, longitude: 72.914, notes: null,
  state: { health_band: 'critical', health_score: 31, last_observed_at: '2026-10-16T10:00:00Z', open_issue_count: 1, open_task_count: 2 },
}

vi.mock('../lib/slice', async (orig) => ({
  ...(await orig<typeof import('../lib/slice')>()),
  useAsset: () => ({ isLoading: false, error: null, data: asset }),
  useTimeline: () => ({ isLoading: false, data: state.timeline }),
  useObservations: () => ({ data: { items: state.obs } }),
  useIssues: () => ({ data: { items: [{ id: 'i1', key: 'GG-001', title: 'Crown dieback', severity: 'high', state: 'open', is_open: true }] } }),
  useTasks: () => ({ data: { items: [{ id: 't1', key: 'T-001', title: 'Inspect the bark', issue_id: 'i1', due_at: '2026-10-27T10:00:00Z', overdue: false }] } }),
  useRecommendations: () => ({ data: { items: [] } }),
  useEvidence: () => ({ data: { items: state.photos } }),
}))
vi.mock('../lib/actions', async (orig) => ({
  ...(await orig<typeof import('../lib/actions')>()),
  useActions: () => ({ data: { history: [{ performed_at: '2026-10-20T08:00:00Z', effective: true, withdrawn: false }] } }),
}))
vi.mock('../components/EvidenceGallery', () => ({
  EvidenceImage: () => <img alt="latest photo" />,
  EvidenceUploader: () => <p>photo uploader</p>,
  EvidenceGallery: ({ labelFor }: { labelFor?: (e: Evidence) => string }) => (
    <ul aria-label="gallery">{(state.photos as Evidence[]).map((p) => <li key={p.id}>{labelFor?.(p)}</li>)}</ul>
  ),
}))
vi.mock('../components/ActionPanel', () => ({ ActionPanel: () => <p>work history</p>, ActionForm: () => <p>work form</p> }))
vi.mock('../components/LifecyclePanel', () => ({ LifecyclePanel: ({ show }: { show: string }) => <p>lifecycle {show}</p> }))
vi.mock('../components/SchedulePanel', () => ({ SchedulePanel: () => <p>schedules</p> }))
vi.mock('../components/HarvestPanel', () => ({ HarvestPanel: () => <p>harvests</p> }))
vi.mock('../pages/GrowthPage', () => ({ GrowthPanel: () => <p>growth</p> }))
vi.mock('../components/asset/ObservationForm', () => ({ ObservationForm: () => <input aria-label="Health score" /> }))

import { AssetProfilePage } from '../pages/AssetProfilePage'

function renderPage(role = 'worker', path = '/w/w1/assets/a1') {
  const ctx = { ws: 'w1', workspace: { id: 'w1', name: 'Campus', mode: 'green_management', role }, capabilities: [] }
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/w/:ws" element={<Outlet context={ctx} />}>
            <Route path="assets/:assetId" element={<AssetProfilePage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const obs = (id: string, at: string, score: number | null) => ({ id, observed_at: at, health_score: score, asset_id: 'a1', symptoms: [], notes: null, data: {}, attachments: [], kind: 'health', source: 'manual', observer_id: null, supersedes_id: null, created_at: at })

beforeEach(() => {
  state.photos = []
  state.obs = [obs('o2', '2026-10-16T10:00:00Z', 31), obs('o1', '2026-09-05T10:00:00Z', 78)]
  state.timeline = [
    { at: '2026-10-20T08:00:00Z', type: 'action', ref_id: 'x1', key: null, title: 'Treatment', detail: '5 litres', actor_id: null },
    { at: '2026-10-16T10:00:00Z', type: 'observation', ref_id: 'o2', key: null, title: 'Observation', detail: 'health 31', actor_id: null },
    { at: '2026-10-15T10:00:00Z', type: 'lifecycle', ref_id: 'l1', key: null, title: 'Lifecycle: Mature', detail: null, actor_id: null },
  ]
})

describe('plant page', () => {
  it('leads with who the plant is: tag, health, stage, open issue and the actions', () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 1, name: 'Neem #102' })).toBeInTheDocument()
    expect(screen.getByText('N-102')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'GG-001' })[0]).toHaveAttribute('href', '/w/w1/issues/i1')
    expect(screen.getByRole('button', { name: 'Record' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add photo' })).toBeInTheDocument()
  })

  it('works out the change between the first and latest recorded scores', () => {
    renderPage()
    const change = screen.getByText('Change').parentElement!
    expect(change).toHaveTextContent('−47')
    expect(change).toHaveTextContent('(78)')
  })

  it('draws the recorded scores with their dates, and says when there are none', () => {
    const { unmount } = renderPage()
    expect(screen.getByRole('img', { name: /2 health scores from .* latest 31/ })).toBeInTheDocument()
    unmount()
    state.obs = [obs('o3', '2026-10-16T10:00:00Z', null)]
    renderPage()
    expect(screen.getByText(/No health score recorded yet/)).toBeInTheDocument()
  })

  it('without a photo, offers to add the first one in the Record sheet', async () => {
    renderPage()
    expect(screen.getByText('No photo yet')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Add the first photo' }))
    const dialog = screen.getByRole('dialog', { name: 'Record for Neem #102' })
    expect(within(dialog).getByRole('tab', { name: 'Photo' })).toHaveAttribute('aria-selected', 'true')
    expect(within(dialog).getByText('photo uploader')).toBeInTheDocument()
  })

  it('labels each photo with the score recorded with it', () => {
    state.photos = [{ id: 'e1', observation_id: 'o2', created_at: '2026-10-16T10:00:00Z' }, { id: 'e2', observation_id: null, created_at: '2026-10-20T10:00:00Z' }]
    renderPage()
    const gallery = screen.getByRole('list', { name: 'gallery' })
    expect(within(gallery).getAllByRole('listitem')[0]).toHaveTextContent(/health 31/)
    expect(within(gallery).getAllByRole('listitem')[1]).not.toHaveTextContent(/health/)
    expect(screen.getByRole('img', { name: 'latest photo' })).toBeInTheDocument()
  })

  it('Record opens one sheet with four kinds of record; Esc closes it', async () => {
    renderPage()
    await userEvent.click(screen.getByRole('button', { name: 'Record' }))
    const dialog = screen.getByRole('dialog', { name: 'Record for Neem #102' })
    expect(within(dialog).getAllByRole('tab').map((t) => t.textContent)).toEqual(['Observation', 'Work done', 'Stage change', 'Photo'])
    expect(within(dialog).getByLabelText('Health score')).toHaveFocus()
    await userEvent.click(within(dialog).getByRole('tab', { name: 'Work done' }))
    expect(within(dialog).getByText('work form')).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('tab', { name: 'Stage change' }))
    expect(within(dialog).getByText('lifecycle form')).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('arriving from the phone Record button opens the sheet', () => {
    renderPage('worker', '/w/w1/assets/a1#record')
    expect(screen.getByRole('dialog', { name: 'Record for Neem #102' })).toBeInTheDocument()
  })

  it('viewers can read everything but cannot record', () => {
    renderPage('viewer', '/w/w1/assets/a1#record')
    expect(screen.queryByRole('button', { name: 'Record' })).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('filters the timeline by kind of record', async () => {
    renderPage()
    const timeline = screen.getByRole('region', { name: 'Timeline' })
    expect(within(timeline).getAllByRole('listitem')).toHaveLength(3)
    await userEvent.click(within(timeline).getByRole('button', { name: 'Work' }))
    expect(within(timeline).getAllByRole('listitem')).toHaveLength(1)
    expect(within(timeline).getByText('Treatment')).toBeInTheDocument()
  })
})
