import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

/* Phase 6 (ADR-074, ADR-075): member management and the two-tab weather page. */

const state = vi.hoisted(() => ({
  role: 'owner',
  settings: {} as Record<string, unknown>,
  add: vi.fn(),
  changeRole: vi.fn(),
  remove: vi.fn(),
  save: vi.fn(),
  forecastCoords: [] as unknown[],
  search: [] as string[],
  locations: [] as unknown[],
  saved: [] as unknown[],
}))

vi.mock('../app/WorkspaceLayout', () => ({
  useWorkspaceCtx: () => ({
    ws: 'w1',
    workspace: { id: 'w1', name: 'Campus', mode: 'green_management', role: state.role, settings: state.settings },
    capabilities: [{ key: 'weather_context', available: true }],
  }),
}))
vi.mock('../lib/auth', () => ({ useAuth: () => ({ user: { id: 'u-me', name: 'Asha' } }) }))
vi.mock('../components/weather/PinMap', () => ({ PinMap: () => <div>map</div> }))

const H = (date: string, h: number, over: Record<string, unknown> = {}) => ({
  time: `${date}T${String(h).padStart(2, '0')}:00:00+05:30`, precipitation_mm: 0, precipitation_probability_pct: 10, temperature_c: 25, et0_mm: 0.2,
  soil_moisture: { '0_to_1cm': 0.3 }, ...over,
})
const FORECAST = {
  latitude: 19.13, longitude: 72.91, timezone: 'Asia/Kolkata', source: 'open_meteo', attribution: 'Weather data by Open-Meteo.com (CC BY 4.0)',
  fetched_at: '2026-10-27T03:00:00Z',
  hourly: ['2026-10-27', '2026-10-28', '2026-10-29'].flatMap((d, i) => [H(d, 6, { temperature_c: 22 + i }), H(d, 14, { temperature_c: 30 + i, precipitation_mm: i === 1 ? 6 : 0, precipitation_probability_pct: i === 1 ? 85 : 10 })]),
}

vi.mock('../lib/queries', () => ({
  useMembers: () => ({
    data: [
      { user_id: 'u-me', name: 'Asha', email: 'asha@x', role: 'owner' },
      { user_id: 'u-r', name: 'Ravi', email: 'ravi@x', role: 'worker' },
      { user_id: 'u-o', name: 'Omar', email: 'omar@x', role: 'owner' },
    ],
  }),
  useMemberChanges: () => ({
    add: { mutate: state.add, isPending: false, error: null },
    changeRole: { mutate: state.changeRole, isPending: false, error: null },
    remove: { mutate: state.remove, isPending: false, error: null },
  }),
  useForecast: (_ws: string, coords: unknown) => {
    state.forecastCoords.push(coords)
    return coords ? { isLoading: false, error: null, data: FORECAST, dataUpdatedAt: Date.parse('2026-10-27T03:00:00Z') } : { isLoading: false, data: undefined }
  },
  usePlaceSearch: (_ws: string, q: string) => {
    state.search.push(q)
    return q.length >= 2
      ? { isFetching: false, error: null, data: { source: 'open_meteo', attribution: 'Place search by Open-Meteo.com (CC BY 4.0)', items: [{ name: 'Pune', region: 'Maharashtra, India', latitude: 18.52, longitude: 73.86 }] } }
      : { isFetching: false, error: null, data: undefined }
  },
  useSavedPlaces: () => ({ isLoading: false, data: state.saved }),
  useWeatherPlaceChanges: () => ({ save: { mutate: state.save, isPending: false, error: null }, remove: { mutate: vi.fn(), isPending: false, error: null } }),
}))
vi.mock('../lib/slice', () => ({
  useLocations: () => ({ isLoading: false, error: null, data: { items: state.locations } }),
  useTasks: () => ({ data: { items: [{ id: 't1', key: 'T-009', title: 'Water the saplings', due_at: '2026-10-28T05:00:00Z', issue_id: null, asset_id: null }] } }),
}))

import { MembersPage } from '../pages/MembersPage'
import { WeatherPage } from '../pages/WeatherPage'

beforeEach(() => {
  state.role = 'owner'
  state.settings = {}
  for (const f of [state.add, state.changeRole, state.remove, state.save]) f.mockReset()
  state.forecastCoords = []
  state.search = []
  state.locations = [{ id: 'l1', name: 'North avenue', kind: 'zone', latitude: 19.13, longitude: 72.91 }]
  state.saved = []
})

describe('members', () => {
  it('an owner adds a member, changes a role and removes someone after confirming; never edits themself', async () => {
    render(<MemoryRouter><MembersPage /></MemoryRouter>)
    const table = screen.getByRole('table', { name: 'Workspace members' })
    const [, me, ravi] = within(table).getAllByRole('row')
    expect(within(me).queryByRole('combobox')).not.toBeInTheDocument()
    expect(me).toHaveTextContent('you')
    await userEvent.selectOptions(within(ravi).getByLabelText('Role for Ravi'), 'manager')
    expect(state.changeRole).toHaveBeenCalledWith({ userId: 'u-r', role: 'manager' })
    await userEvent.click(within(ravi).getByRole('button', { name: 'Remove' }))
    expect(state.remove).not.toHaveBeenCalled()
    await userEvent.click(within(ravi).getByRole('button', { name: 'Remove Ravi from this workspace' }))
    expect(state.remove.mock.calls[0][0]).toBe('u-r')

    await userEvent.click(screen.getByRole('button', { name: 'Add a member' }))
    const form = screen.getByRole('form', { name: 'Add a member' })
    await userEvent.type(within(form).getByLabelText('Email'), 'meera@x')
    await userEvent.click(within(form).getByRole('button', { name: 'Add' }))
    expect(state.add.mock.calls[0][0]).toEqual({ email: 'meera@x', role: 'worker' })
  })

  it('an admin cannot give or touch the owner role; others only read', () => {
    state.role = 'admin'
    const { unmount } = render(<MemoryRouter><MembersPage /></MemoryRouter>)
    const omar = within(screen.getByRole('table')).getAllByRole('row')[3]
    expect(within(omar).queryByRole('combobox')).not.toBeInTheDocument()
    const ravi = within(screen.getByRole('table')).getAllByRole('row')[2]
    expect(within(within(ravi).getByLabelText('Role for Ravi')).queryByRole('option', { name: 'Owner' })).not.toBeInTheDocument()
    unmount()
    state.role = 'manager'
    render(<MemoryRouter><MembersPage /></MemoryRouter>)
    expect(screen.queryByRole('button', { name: 'Add a member' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.getByText(/Only owners and admins/)).toBeInTheDocument()
  })
})

describe('weather', () => {
  it('My places: a week for a zone, a day to look into, work due that day and the rain rule applied', async () => {
    render(<MemoryRouter><WeatherPage /></MemoryRouter>)
    expect(state.forecastCoords.at(-1)).toEqual({ lat: 19.13, lon: 72.91, days: 7 })
    const week = screen.getByRole('region', { name: 'Next 7 days' })
    const days = within(week).getAllByRole('button')
    expect(days).toHaveLength(3)
    expect(days[0]).toHaveAttribute('aria-pressed', 'true')
    expect(days[1]).toHaveTextContent('Rain likely')
    expect(days[1]).toHaveTextContent('1 task due')
    await userEvent.click(days[1])
    expect(screen.getByRole('region', { name: /Work due/ })).toHaveTextContent('T-009')
    expect(screen.getByRole('img', { name: /Temperature by the hour: from 23 °C to 31 °C, highest at 14:00/ })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Rain' }))
    expect(screen.getByRole('img', { name: /Rain by the hour/ })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: /Rain advice/ })).toHaveTextContent(/at least 5 mm is 70% likely/)
  })

  it('My places without coordinates points to Any place', async () => {
    state.locations = [{ id: 'l1', name: 'North avenue', kind: 'zone', latitude: null, longitude: null }]
    render(<MemoryRouter><WeatherPage /></MemoryRouter>)
    expect(screen.getByText('No place with coordinates yet')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Find a place' }))
    expect(screen.getByRole('tab', { name: 'Any place' })).toHaveAttribute('aria-selected', 'true')
  })

  it('Any place: search, pick, see three days, and save it (managers)', async () => {
    render(<MemoryRouter><WeatherPage /></MemoryRouter>)
    await userEvent.click(screen.getByRole('tab', { name: 'Any place' }))
    await userEvent.type(screen.getByLabelText('Area, town or village'), 'Pune')
    await userEvent.click(await within(await screen.findByRole('list', { name: 'Places found' })).findByRole('button', { name: /Pune/ }))
    expect(state.forecastCoords.at(-1)).toEqual({ lat: 18.52, lon: 73.86, days: 3 })
    expect(screen.getByRole('heading', { name: 'Pune, next 3 days' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Save to my places' }))
    expect(state.save.mock.calls[0][0]).toEqual({ name: 'Pune', region: 'Maharashtra, India', latitude: 18.52, longitude: 73.86 })
  })

  it('Any place: workers see the forecast but cannot save', async () => {
    state.role = 'worker'
    render(<MemoryRouter><WeatherPage /></MemoryRouter>)
    await userEvent.click(screen.getByRole('tab', { name: 'Any place' }))
    await userEvent.type(screen.getByLabelText('Area, town or village'), 'Pune')
    await userEvent.click(await within(await screen.findByRole('list', { name: 'Places found' })).findByRole('button', { name: /Pune/ }))
    expect(screen.queryByRole('button', { name: 'Save to my places' })).not.toBeInTheDocument()
    expect(screen.getByText(/Managers and owners can save places/)).toBeInTheDocument()
  })
})
