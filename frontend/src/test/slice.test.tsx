import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Recommendation } from '../api/types'
import { HealthChip, MethodBadge, SeverityChip } from '../components/domain'
import { RecommendationCard } from '../components/RecommendationCard'
import { atLeast, label, relative } from '../lib/format'
import { qs } from '../lib/slice'

const rec: Recommendation = {
  id: 'r1', rule_key: 'critical_health', method: 'rule', asset_id: 'a1', title: 'Neem #482 health is critical (22)',
  explanation: 'latest health score 22 is below the critical threshold 40 and the asset has no open issue',
  evidence: {}, proposed_action: { create: 'issue' }, severity: 'high', status: 'open', accepted_entity_type: null,
  accepted_entity_id: null, dismissed_reason: null, created_at: new Date().toISOString(), decided_at: null,
  agent_run_id: null, rule_version: 1, outcome: null, outcome_at: null, outcome_detail: null,
}

function renderCard(canDecide: boolean, over: Partial<Recommendation> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ul><RecommendationCard rec={{ ...rec, ...over }} ws="w1" canDecide={canDecide} /></ul>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('format helpers', () => {
  const now = new Date('2026-10-07T12:00:00Z')
  it('describes times relative to now', () => {
    expect(relative(null, now)).toBe('never')
    expect(relative('2026-10-07T11:59:40Z', now)).toBe('just now')
    expect(relative('2026-10-04T12:00:00Z', now)).toBe('3 days ago')
    expect(relative('2026-10-09T12:00:00Z', now)).toBe('in 2 days')
    expect(relative('2026-10-07T09:00:00Z', now)).toBe('3 h ago')
  })
  it('mirrors the server role ladder', () => {
    expect(atLeast('worker', 'worker')).toBe(true)
    expect(atLeast('viewer', 'worker')).toBe(false)
    expect(atLeast('manager', 'worker')).toBe(true)
    expect(atLeast('worker', 'manager')).toBe(false)
  })
  it('builds query strings without empty values', () => {
    expect(qs({ a: 1, b: '', c: undefined, d: null, e: false, f: 'x y' })).toBe('?a=1&e=false&f=x+y')
    expect(qs({})).toBe('')
  })
  it('humanises snake_case', () => expect(label('water_stress')).toBe('Water stress'))
})

describe('status chips never invent state', () => {
  it('shows "No health data" for an unobserved asset instead of a healthy-looking default', () => {
    render(<HealthChip band={null} />)
    expect(screen.getByText('No health data')).toBeInTheDocument()
  })
  it('carries the band and score as text, not colour alone', () => {
    render(<HealthChip band="at_risk" score={61.4} />)
    expect(screen.getByText(/At risk · 61/)).toBeInTheDocument()
  })
  it('labels the method that produced an output', () => {
    render(<><MethodBadge method="rule" /><MethodBadge method="statistical" /><SeverityChip severity="high" /></>)
    expect(screen.getByText('Rule')).toBeInTheDocument()
    expect(screen.getByText('Statistical')).toBeInTheDocument()
    expect(screen.getByText('High')).toBeInTheDocument()
  })
})

describe('RecommendationCard', () => {
  it('explains itself and says it is not a prediction', async () => {
    renderCard(true)
    expect(screen.getByText('Rule')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Why?' }))
    expect(screen.getByText(/below the critical threshold 40/)).toBeInTheDocument()
    expect(screen.getByText(/this is not a prediction/)).toBeInTheDocument()
  })
  it('only offers accept and dismiss to people who can decide', () => {
    renderCard(false)
    expect(screen.queryByRole('button', { name: /Accept/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Dismiss' })).not.toBeInTheDocument()
    expect(screen.getByText(/A manager decides/)).toBeInTheDocument()
  })
  it('requires a reason before a dismissal can be confirmed', async () => {
    renderCard(true)
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    const confirm = screen.getByRole('button', { name: 'Confirm dismiss' })
    expect(confirm).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Reason for dismissing'), 'Tree removal booked')
    expect(confirm).toBeEnabled()
  })
  it('posts the acceptance and surfaces a server problem', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ code: 'recommendation_not_open', detail: 'recommendation is already accepted', status: 409 }), { status: 409, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)
    renderCard(true)
    await userEvent.click(screen.getByRole('button', { name: 'Accept: open issue' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('already accepted')
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toContain('/workspaces/w1/recommendations/r1/accept')
    expect(init.method).toBe('POST')
  })
})

describe('RecommendationCard: irrigation advice and outcomes', () => {
  const irrigation: Partial<Recommendation> = {
    rule_key: 'irrigation_defer', severity: 'low', title: 'Consider deferring watering of Mango #7 (T-004): 14 mm rain forecast',
    explanation: 'ADVISORY, based on a weather forecast and not on a measurement of soil moisture. 14 mm of rain is forecast.',
    proposed_action: { create: 'defer_task', task_id: 't1' }, rule_version: 1,
    evidence: { evaluated_at: '2026-10-18T06:00:00Z', rule: { key: 'irrigation_defer', version: 1 }, inputs: {
      kind: 'advisory_forecast_based', forecast: { source: 'open-meteo', as_of: '2026-10-18T06:00:00Z' },
      not_known: ['measured soil moisture (a coarse model estimate is shown, not a sensor reading)', 'observed rainfall (only a forecast is available)'],
    } },
  }
  it('labels forecast-based advice as advisory and lists what the rule does not know', async () => {
    renderCard(true, irrigation)
    expect(screen.getByText(/Advisory · forecast-based/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Why?' }))
    expect(screen.getByText(/a forecast is not a measurement of soil moisture/)).toBeInTheDocument()
    expect(screen.queryByText(/this is not a prediction/)).not.toBeInTheDocument()
    expect(screen.getByText('Not known to this rule:')).toBeInTheDocument()
    expect(screen.getByText(/observed rainfall/)).toBeInTheDocument()
    expect(screen.getByText(/Forecast source: open-meteo/)).toBeInTheDocument()
    expect(screen.queryByText(/\.\./)).not.toBeInTheDocument() // no doubled full stop after an explanation that already ends in one
  })
  it('offers to postpone the watering task, never to water or skip it automatically', () => {
    renderCard(true, irrigation)
    expect(screen.getByRole('button', { name: 'Accept: postpone the watering task' })).toBeInTheDocument()
  })
  it('shows the outcome and hides the actions once the advice has been acted on', () => {
    renderCard(true, { ...irrigation, status: 'accepted', outcome: 'deferral_applied', outcome_at: '2026-10-18T07:00:00Z', outcome_detail: 'task T-004 due date moved to 2026-10-19T12:00:00+00:00' })
    expect(screen.getByText('Task postponed')).toBeInTheDocument()
    expect(screen.getByText(/due date moved to/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Accept/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Dismiss' })).not.toBeInTheDocument()
  })
  it('shows why a dismissed or expired suggestion is no longer open', () => {
    const { unmount } = renderCard(true, { status: 'dismissed', dismissed_reason: 'Hand-watering anyway' })
    expect(screen.getByText(/Dismissed: Hand-watering anyway/)).toBeInTheDocument()
    unmount()
    renderCard(true, { status: 'expired' })
    expect(screen.getByText('Expired')).toBeInTheDocument()
    expect(screen.queryByText(/A manager decides/)).not.toBeInTheDocument()
  })
})
