import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ProblemError } from '../api/client'
import type { ProtocolContentRecord, ProtocolDetailRecord, ProtocolSummaryRecord, Role } from '../api/types'

type Q = Record<string, unknown>
const idle = () => ({ mutate: vi.fn(), isPending: false, error: null as unknown })
const state = vi.hoisted(() => ({
  q: {} as Record<string, Q>,
  mut: {} as Record<string, { mutate: ReturnType<typeof vi.fn>; isPending: boolean; error: unknown }>,
}))

vi.mock('../lib/protocols', () => ({
  useProtocols: () => state.q.list,
  useProtocol: () => state.q.detail,
  useProtocolTemplate: () => state.q.template,
  useCreateProtocol: () => state.mut.create,
  useSignoff: () => state.mut.sign,
}))

import { ProtocolDetailPage, ProtocolsPage } from '../pages/ProtocolsPage'

const ok = (data: unknown): Q => ({ isLoading: false, error: null, data, refetch: vi.fn() })

const content = (): ProtocolContentRecord => ({
  title: 'P-DIS-1: photo-based leaf-disease triage assistant (proposal)', intended_use: 'Decision support from smartphone photographs.',
  not_for: ['diagnosis', 'pesticide decisions'], target_population: 'Growers and field staff using ordinary phones outdoors.',
  species: ['potato (initial candidate)'], disease_classes: ['healthy', 'early blight', 'late blight', 'other/unknown'],
  inclusion_criteria: ['outdoor RGB photograph'], exclusion_criteria: ['laboratory backgrounds'], dataset_requirements: ['approved datasets only'],
  label_requirements: ['two independent reviewers'],
  grouping: { hierarchy: ['farm or site', 'plot', 'plant'], test_split_unit: 'whole farms never seen in training', claim_downgrade_if_no_site: 'Without site data the claim is limited to photographs like those in the dataset.' },
  methodology: ['fixed before training'], baselines: ['majority class'], metrics: ['per-class recall'], confidence_and_calibration: ['Wilson 95% intervals'],
  error_costs: { false_negative: 'A missed disease delays treatment.', false_positive: 'A false alarm wastes treatment.', operating_point: 'Chosen on validation.' },
  thresholds: [
    { id: 'test_images_per_class', metric: 'test images per class', scope: 'every class in a claim', comparator: 'ge', value: 139, basis: 'statistical_derivation', requires_domain_expertise: false, status: 'proposed', justification: 'n = z^2 p(1-p)/h^2 gives 138.3, rounded up.' },
    { id: 'recall_lower_bound', metric: 'lower 95% bound of recall', scope: 'each disease class', comparator: 'ge', value: null, basis: 'pending_domain_input', requires_domain_expertise: true, status: 'pending_domain_approval', justification: 'Depends on the cost of a missed disease; no value proposed.' },
  ],
  required_signoffs: ['plant_pathologist', 'data_owner', 'independent_evaluator'], prohibited_claims: ['any claim from unreviewed labels'], limitations: ['the application cannot verify qualifications'],
})
const summary = (over: Partial<ProtocolSummaryRecord> = {}): ProtocolSummaryRecord => ({
  id: 'p1', key: 'p-dis-1', version: 1, title: 'P-DIS-1: photo-based leaf-disease triage assistant (proposal)', content_sha256: 'a'.repeat(64),
  created_by: 'user-aaaa', created_at: '2026-10-18T00:00:00Z', is_proposal_only: true,
  status: { state: 'awaiting_signoffs', blockers: ['awaiting sign-off from: plant_pathologist, data_owner, independent_evaluator'], signed_roles: [] }, ...over,
})
const detail = (over: Partial<ProtocolDetailRecord> = {}): ProtocolDetailRecord => ({ ...summary(), content: content(), signoffs: [], ...over })

function page(role: Role, path: string) {
  const ctx = { ws: 'w1', workspace: { id: 'w1', name: 'City', mode: 'green_management', role }, capabilities: [] }
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/w/:ws" element={<Outlet context={ctx} />}>
          <Route path="ai/protocols" element={<ProtocolsPage />} />
          <Route path="ai/protocols/:protocolId" element={<ProtocolDetailPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}
const list = (role: Role) => page(role, '/w/w1/ai/protocols')
const one = (role: Role) => page(role, '/w/w1/ai/protocols/p1')

beforeEach(() => {
  state.q = {
    list: ok({ items: [], total: 0, limit: 100, offset: 0 }),
    detail: ok(detail()),
    template: ok({ content: content(), note: 'A proposal. It is not approved.', required_roles: ['plant_pathologist', 'data_owner', 'independent_evaluator'] }),
  }
  state.mut = { create: idle(), sign: idle() }
})

describe('protocol list', () => {
  it('says plainly that no protocol is approved and why approval is unreachable', () => {
    list('viewer')
    expect(screen.getByText(/No model exists and no protocol here is approved/)).toBeInTheDocument()
    expect(screen.getByText(/cannot verify it, so approval is not reachable yet/)).toBeInTheDocument()
    expect(screen.getByText('No protocol is registered')).toBeInTheDocument()
  })

  it('shows loading, error and permission-denied states', () => {
    state.q.list = { isLoading: true, error: null, data: undefined, refetch: vi.fn() }
    const a = list('viewer')
    expect(screen.getByText(/loading protocols/i)).toBeInTheDocument()
    a.unmount()
    state.q.list = { isLoading: false, error: new ProblemError(403, 'insufficient_role', 'no'), data: undefined, refetch: vi.fn() }
    list('viewer')
    expect(screen.getByText('You do not have access to this')).toBeInTheDocument()
  })

  it('lists versions with their computed state and never as approved', () => {
    state.q.list = ok({ total: 2, limit: 100, offset: 0, items: [
      summary(),
      summary({ id: 'p2', version: 2, status: { state: 'awaiting_qualification_verification', blockers: ['qualifications are not verified for: plant_pathologist'], signed_roles: ['plant_pathologist'] } }),
    ] })
    list('viewer')
    expect(screen.getByText('Not approved: awaiting sign-offs')).toBeInTheDocument()
    expect(screen.getByText('Not approved: qualifications unverified')).toBeInTheDocument()
    expect(screen.queryByText('Approved')).not.toBeInTheDocument()
  })

  it('offers registration only to managers and submits the template content', async () => {
    const v = list('viewer')
    expect(screen.queryByRole('button', { name: 'Register the proposed protocol' })).not.toBeInTheDocument()
    v.unmount()
    list('manager')
    await userEvent.click(screen.getByRole('button', { name: 'Register the proposed protocol' }))
    expect(screen.getByText(/Thresholds that need domain expertise are included without values/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Register as a new version' }))
    const body = state.mut.create.mutate.mock.calls[0][0] as { key: string; content: ProtocolContentRecord }
    expect(body.key).toBe('p-dis-1')
    expect(body.content.thresholds.find((t) => t.id === 'recall_lower_bound')?.value).toBeNull() // no value is invented on the way
  })

  it('shows the server refusal of an invalid protocol', async () => {
    state.mut.create.error = new ProblemError(422, 'validation_error', 'threshold must not carry an invented value')
    list('manager')
    await userEvent.click(screen.getByRole('button', { name: 'Register the proposed protocol' }))
    expect(screen.getByRole('alert')).toHaveTextContent('invented value')
  })
})

describe('protocol detail', () => {
  it('shows the plan and the reasons it is not approved', () => {
    one('viewer')
    expect(screen.getByText('Not approved: awaiting sign-offs')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Why this protocol is not approved' })).toHaveTextContent('awaiting sign-off from')
    expect(screen.getByText('Decision support from smartphone photographs.')).toBeInTheDocument()
    expect(screen.getByText(/Hierarchy: farm or site > plot > plant/)).toBeInTheDocument()
    expect(screen.getByText('Claims that are prohibited')).toBeInTheDocument()
  })

  it('never shows a value for a threshold that needs domain expertise', () => {
    one('viewer')
    const pending = screen.getByText('lower 95% bound of recall').closest('li') as HTMLElement
    expect(within(pending).getByText('≥ no value proposed')).toBeInTheDocument() // the value itself is absent, not zero
    expect(within(pending).getByText('Pending domain approval')).toBeInTheDocument()
    const derived = screen.getByText('test images per class').closest('li') as HTMLElement
    expect(within(derived).getByText(/≥ 139/)).toBeInTheDocument()
    expect(within(derived).getByText('Proposed, needs sign-off')).toBeInTheDocument()
    expect(screen.getByText(/Nothing here is an agreed acceptance criterion/)).toBeInTheDocument()
  })

  it('labels every sign-off qualification as declared and unverified', () => {
    state.q.detail = ok(detail({ signoffs: [
      { id: 's1', role: 'plant_pathologist', decision: 'approve', signer_id: 'signer-0001', declared_qualification: 'agronomy graduate', qualification_verified: false, note: 'reviewed the class list', at: '2026-10-18T10:00:00Z' },
      { id: 's2', role: 'data_owner', decision: 'approve', signer_id: 'signer-0002', declared_qualification: null, qualification_verified: false, note: 'licences checked', at: '2026-10-18T11:00:00Z' },
    ] }))
    one('viewer')
    expect(screen.getByText(/Declared qualification: “agronomy graduate”/)).toHaveTextContent('unverified')
    expect(screen.getByText(/No qualification declared/)).toHaveTextContent('unverified')
    expect(screen.queryByText(/— verified/)).not.toBeInTheDocument()
  })

  it('does not call a fully signed protocol approved while qualifications are unverified', () => {
    state.q.detail = ok(detail({ status: { state: 'awaiting_qualification_verification', blockers: ['qualifications are not verified for: plant_pathologist, data_owner, independent_evaluator'], signed_roles: ['plant_pathologist', 'data_owner', 'independent_evaluator'] } }))
    one('manager')
    expect(screen.getByText('Not approved: qualifications unverified')).toBeInTheDocument()
    expect(screen.queryByText('Approved')).not.toBeInTheDocument()
  })

  it('gives viewers no sign-off form and managers a form that does not name the signer', async () => {
    const v = one('viewer')
    expect(screen.getByText(/Only managers and owners can record a sign-off/)).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Record a sign-off' })).not.toBeInTheDocument()
    v.unmount()
    one('manager')
    const record = screen.getByRole('button', { name: 'Record sign-off' })
    expect(record).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/Note: what you checked/), 'checked the grouping and metrics')
    await userEvent.type(screen.getByLabelText(/Your qualification/), 'statistician (self-declared)')
    await userEvent.click(record)
    const body = state.mut.sign.mutate.mock.calls[0][0] as Record<string, unknown>
    expect(body).toEqual({ role: 'independent_evaluator', decision: 'approve', declared_qualification: 'statistician (self-declared)', note: 'checked the grouping and metrics' })
    expect(Object.keys(body)).not.toContain('signer_id')
    expect(screen.getByLabelText(/Your qualification/).closest('div')).toHaveTextContent('does not verify it')
  })

  it('shows the server refusing a data-owner sign-off from a non-owner', async () => {
    state.mut.sign.error = new ProblemError(403, 'forbidden', 'only the workspace owner can sign as the data owner')
    one('manager')
    expect(screen.getByRole('alert')).toHaveTextContent('only the workspace owner')
  })

  it('tells people to sign the newest version of a superseded protocol', () => {
    state.q.detail = ok(detail({ status: { state: 'superseded', blockers: ['a newer version of this protocol exists'], signed_roles: [] } }))
    one('manager')
    expect(screen.getByText('Superseded by a newer version')).toBeInTheDocument()
    expect(screen.getByText(/sign the newest version/)).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Record a sign-off' })).not.toBeInTheDocument()
  })

  it('shows loading and error states', () => {
    state.q.detail = { isLoading: true, error: null, data: undefined, refetch: vi.fn() }
    const a = one('viewer')
    expect(screen.getByText(/loading protocol/i)).toBeInTheDocument()
    a.unmount()
    state.q.detail = { isLoading: false, error: new ProblemError(404, 'protocol_not_found', 'Protocol not found'), data: undefined, refetch: vi.fn() }
    one('viewer')
    expect(screen.getByRole('alert')).toHaveTextContent('Protocol not found')
  })
})
