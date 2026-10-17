import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AuditEvent } from '../api/types'

const state = vi.hoisted(() => ({
  list: {} as Record<string, unknown>,
  meta: {} as Record<string, unknown>,
  calls: [] as { params: Record<string, unknown>; enabled: boolean }[],
  metaEnabled: [] as boolean[],
}))

vi.mock('../lib/slice', () => ({
  useAudit: (_ws: string, params: Record<string, unknown>, enabled = true) => { state.calls.push({ params, enabled }); return state.list },
  useAuditMeta: (_ws: string, enabled = true) => { state.metaEnabled.push(enabled); return state.meta },
}))

import { AuditPage } from '../pages/AuditPage'

const event = (n: number, over: Partial<AuditEvent> = {}): AuditEvent => ({
  id: `e${n}`, occurred_at: '2026-10-18T10:00:00Z', actor_id: 'u1', actor_name: 'Worker', action: 'asset.create', outcome: 'success',
  target_type: 'asset', target_id: `aaaaaaaa-0000-0000-0000-00000000000${n}`, request_id: `req-id-000000${n}`, client_ip: '10.0.0.1',
  details: { label: 'Neem #1' }, ...over,
})
const meta = { actions: ['asset.create', 'access.denied'], target_types: ['asset', 'issue'], retention_days: 730, min_retention_days: 30 }

function show(role: 'manager' | 'worker' = 'manager') {
  const ctx = { ws: 'w1', workspace: { id: 'w1', name: 'City', mode: 'green_management', role }, capabilities: [] }
  return render(
    <MemoryRouter initialEntries={['/w/w1/settings/audit']}>
      <Routes>
        <Route path="/w/:ws" element={<Outlet context={ctx} />}>
          <Route path="settings/audit" element={<AuditPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}
const lastParams = () => state.calls[state.calls.length - 1].params

describe('audit log page', () => {
  beforeEach(() => {
    state.calls = []
    state.metaEnabled = []
    state.meta = { data: meta, isLoading: false, error: null }
    state.list = { isLoading: false, error: null, data: undefined, refetch: vi.fn() }
  })

  it('shows loading and error states', () => {
    state.list = { ...state.list, isLoading: true }
    const { unmount } = show()
    expect(screen.getByText(/loading audit log/i)).toBeInTheDocument()
    unmount()
    state.list = { ...state.list, isLoading: false, error: new Error('boom') }
    show()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('explains an empty trail and an empty filter result differently', async () => {
    state.list = { ...state.list, data: { items: [], total: 0, limit: 25, offset: 0 } }
    show()
    expect(screen.getByText('No audit events yet')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Request ID'), 'abc')
    await userEvent.click(screen.getByRole('button', { name: 'Apply filters' }))
    expect(screen.getByText('No events match these filters')).toBeInTheDocument()
  })

  it('populated: actors, actions, outcomes, targets, request IDs and escaped details', async () => {
    state.list = {
      ...state.list,
      data: {
        total: 3, limit: 25, offset: 0,
        items: [
          event(1),
          event(2, { actor_id: null, actor_name: null, action: 'access.denied', outcome: 'denied', target_type: null, target_id: null, details: { reason: 'insufficient_role', route: '/x/<script>alert(1)</script>' } }),
          event(3, { target_type: 'issue', outcome: 'failure', request_id: null }),
        ],
      },
    }
    show()
    expect(screen.getByText('3 events, newest first.')).toBeInTheDocument()
    const rows = screen.getAllByRole('row').slice(1)
    expect(within(rows[0]).getByText('Worker')).toBeInTheDocument()
    expect(within(rows[0]).getByRole('link', { name: 'aaaaaaaa' })).toHaveAttribute('href', '/w/w1/assets/aaaaaaaa-0000-0000-0000-000000000001')
    expect(within(rows[1]).getByText(/system \/ not signed in/)).toBeInTheDocument()
    expect(within(rows[1]).getByText('denied')).toBeInTheDocument()
    expect(within(rows[2]).getByRole('link', { name: 'aaaaaaaa' })).toHaveAttribute('href', '/w/w1/issues/aaaaaaaa-0000-0000-0000-000000000003')
    // details are shown as text, never interpreted as markup
    await userEvent.click(within(rows[1]).getByText('Details'))
    expect(document.querySelector('script')).toBeNull()
    expect(within(rows[1]).getByText(/<script>alert\(1\)<\/script>/)).toBeInTheDocument()
  })

  it('filters are sent to the server and reset clears them', async () => {
    state.list = { ...state.list, data: { items: [event(1)], total: 1, limit: 25, offset: 0 } }
    show()
    await userEvent.selectOptions(screen.getByLabelText('Action'), 'access.denied')
    await userEvent.selectOptions(screen.getByLabelText('Target type'), 'issue')
    await userEvent.type(screen.getByLabelText('Request ID'), '  req-xyz-12345 ')
    await userEvent.click(screen.getByRole('button', { name: 'Apply filters' }))
    expect(lastParams()).toMatchObject({ action: 'access.denied', target_type: 'issue', request_id: 'req-xyz-12345', offset: 0, limit: 25 })
    await userEvent.click(screen.getByRole('button', { name: 'Reset' }))
    expect(lastParams()).toMatchObject({ action: undefined, target_type: undefined, request_id: undefined })
  })

  it('clicking a request ID narrows the log to that request', async () => {
    state.list = { ...state.list, data: { items: [event(1)], total: 1, limit: 25, offset: 0 } }
    show()
    await userEvent.click(screen.getByRole('button', { name: /req-id-000…/ }))
    expect(lastParams()).toMatchObject({ request_id: 'req-id-0000001' })
    expect((screen.getByLabelText('Request ID') as HTMLInputElement).value).toBe('req-id-0000001')
  })

  it('paginates', async () => {
    state.list = { ...state.list, data: { items: [event(1)], total: 60, limit: 25, offset: 0 } }
    show()
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(lastParams()).toMatchObject({ offset: 25 })
  })

  it('states the retention policy, and says so when records are kept forever', () => {
    state.list = { ...state.list, data: { items: [event(1)], total: 1, limit: 25, offset: 0 } }
    const { unmount } = show()
    expect(screen.getByText(/kept for 730 days/)).toBeInTheDocument()
    unmount()
    state.meta = { data: { ...meta, retention_days: 0 }, isLoading: false, error: null }
    show()
    expect(screen.getByText('Records are kept indefinitely.')).toBeInTheDocument()
  })

  it('people below manager see a permission message and issue no requests', () => {
    show('worker')
    expect(screen.getByText('You do not have access to this')).toBeInTheDocument()
    expect(screen.getByText(/only managers and owners/i)).toBeInTheDocument()
    expect(state.calls.every((c) => c.enabled === false)).toBe(true)
    expect(state.metaEnabled.every((e) => e === false)).toBe(true)
  })
})
