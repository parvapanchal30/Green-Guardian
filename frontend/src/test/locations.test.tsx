import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LocationItem } from '../api/types'

const state = vi.hoisted(() => ({ items: [] as unknown[], create: vi.fn(), role: 'manager', mode: 'agricultural_production' }))

vi.mock('../lib/slice', async (orig) => ({
  ...(await orig<typeof import('../lib/slice')>()),
  useLocations: () => ({ isLoading: false, error: null, data: { items: state.items, total: state.items.length } }),
  useCreateLocation: () => ({ mutate: state.create, isPending: false, error: null }),
}))
vi.mock('../components/SchedulePanel', () => ({
  SchedulePanel: ({ location }: { location: LocationItem }) => <p>schedules of {location.name}</p>,
}))
vi.mock('../app/WorkspaceLayout', () => ({
  useWorkspaceCtx: () => ({ ws: 'w1', workspace: { id: 'w1', mode: state.mode, role: state.role }, capabilities: [] }),
}))

import { LocationsPage } from '../pages/LocationsPage'

const loc = (over: Partial<LocationItem>): LocationItem => ({
  id: 'l1', name: 'Valley fields', kind: 'site', parent_id: null, latitude: 18.52, longitude: 73.85, attributes: {},
  assets: 0, needs_attention: 0, schedules: 0, ...over,
})

const page = () => render(<MemoryRouter><LocationsPage /></MemoryRouter>)

beforeEach(() => {
  state.create.mockReset()
  state.role = 'manager'
  state.mode = 'agricultural_production'
  state.items = [loc({}), loc({ id: 'l2', name: 'North block', kind: 'field', parent_id: 'l1', latitude: null, longitude: null, assets: 3, needs_attention: 1, schedules: 2 })]
})

describe('fields and zones', () => {
  it('lists places with what is in them, what needs attention and their recurring checks', async () => {
    page()
    expect(screen.getByRole('heading', { name: 'Fields' })).toBeInTheDocument() // the mode's word
    const north = screen.getAllByRole('listitem')[1]
    for (const text of ['North block', 'Field', 'in Valley fields', '1 needs attention', '2 recurring inspections', 'no coordinates']) expect(north).toHaveTextContent(text)
    expect(within(north).getByRole('link', { name: '3 living assets' })).toHaveAttribute('href', '/w/w1/assets?location=l2')
    await userEvent.click(within(north).getByRole('button', { name: 'Recurring inspections' }))
    expect(screen.getByText('schedules of North block')).toBeInTheDocument()
  })

  it('a manager adds a place inside another, with coordinates given together', async () => {
    page()
    await userEvent.click(screen.getByRole('button', { name: 'Add a place' }))
    const form = screen.getByRole('form', { name: 'Add a place' })
    expect((within(form).getByLabelText('Kind') as HTMLSelectElement).value).toBe('field')
    await userEvent.type(within(form).getByLabelText('Name'), 'South block')
    await userEvent.selectOptions(within(form).getByLabelText('Inside (optional)'), 'l1')
    await userEvent.type(within(form).getByLabelText('Latitude'), '18.5')
    await userEvent.click(within(form).getByRole('button', { name: 'Save the place' }))
    expect(screen.getByRole('alert')).toHaveTextContent('both latitude and longitude')
    await userEvent.type(within(form).getByLabelText('Longitude'), '73.8')
    await userEvent.click(within(form).getByRole('button', { name: 'Save the place' }))
    expect(state.create).toHaveBeenCalledWith({ name: 'South block', kind: 'field', parent_id: 'l1', latitude: 18.5, longitude: 73.8 }, expect.anything())
  })

  it('a worker sees the places but cannot add one; a green workspace calls them zones', () => {
    state.role = 'worker'
    state.mode = 'green_management'
    page()
    expect(screen.getByRole('heading', { name: 'Zones' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add a place' })).not.toBeInTheDocument()
  })
})
