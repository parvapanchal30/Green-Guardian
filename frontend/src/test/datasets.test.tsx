import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ProblemError } from '../api/client'
import type { DatasetDetailRecord, DatasetItem, DatasetSampleRecord, Role } from '../api/types'

type Q = Record<string, unknown>
const idle = () => ({ mutate: vi.fn(), isPending: false, error: null as unknown })
const state = vi.hoisted(() => ({
  q: {} as Record<string, Q>,
  mut: {} as Record<string, { mutate: ReturnType<typeof vi.fn>; isPending: boolean; error: unknown }>,
  sampleParams: [] as Record<string, unknown>[],
}))

vi.mock('../lib/datasets', () => ({
  useLicencePolicy: () => state.q.policy,
  useDatasets: () => state.q.list,
  useDataset: () => state.q.dataset,
  useDatasetSamples: (_ws: string, _id: string, params: Record<string, unknown>) => { state.sampleParams.push(params); return state.q.samples },
  useSampleReviews: () => state.q.reviews,
  useReviewSummary: () => state.q.summary,
  useDatasetQuality: () => state.q.quality,
  useDatasetAgreement: () => state.q.agreement,
  useDatasetSplits: () => state.q.splits,
  useClaimReadiness: () => state.q.claims,
  useCreateDataset: () => state.mut.create,
  useAddEvidence: () => state.mut.evidence,
  useTransitionDataset: () => state.mut.transition,
  useReviewSample: () => state.mut.review,
  useCreateSplit: () => state.mut.split,
}))

import { DatasetDetailPage } from '../pages/DatasetDetailPage'
import { DatasetsPage } from '../pages/DatasetsPage'

const ok = (data: unknown): Q => ({ isLoading: false, error: null, data, refetch: vi.fn() })

const dataset = (over: Partial<DatasetDetailRecord> = {}): DatasetDetailRecord => ({
  id: 'd1', name: 'Example leaf set', version: '1', kind: 'real', source_url: 'https://data.example.org/leaves', accessed_at: '2026-10-18T00:00:00Z',
  licence_spdx: 'CC-BY-4.0', images_licence_spdx: 'CC-BY-4.0', annotations_licence_spdx: null, has_annotations: false, image_origin: 'unknown',
  attribution_required: true, attribution_text: 'Doe 2024', commercial_use: 'yes', redistribution: 'yes', intended_use: 'Research baseline', notes: null,
  status: 'under_review', created_by: 'user-aaaa', created_at: '2026-10-18T00:00:00Z', approved_by: null, approved_at: null, licence_verdict: 'eligible',
  blockers: ['image origin is \'unknown\': a publisher\'s licence only covers images the publisher had the right to license'], download_allowed: false,
  is_biological_data: true, evidence: [], history: [{ from_status: null, to_status: 'proposed', actor_id: 'user-aaaa', note: 'Dataset proposed', blockers: [], at: '2026-10-18T00:00:00Z' }],
  sample_count: 0, ...over,
})
const item = (over: Partial<DatasetItem> = {}): DatasetItem => {
  const { evidence: _e, history: _h, sample_count: _s, ...rest } = dataset(over)
  return rest
}
const sample = (over: Partial<DatasetSampleRecord> = {}): DatasetSampleRecord => ({
  id: 's1', external_id: 'item-0001', group_key: 'g1', label: 'blight', label_status: 'unreviewed', content_sha256: null, phash: null, file_status: 'ok',
  width: 128, height: 128, provenance: {}, is_synthetic: true, version: 1, ...over,
})

function page(role: Role, path = '/w/w1/ai/datasets') {
  const ctx = { ws: 'w1', workspace: { id: 'w1', name: 'City', mode: 'green_management', role }, capabilities: [] }
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/w/:ws" element={<Outlet context={ctx} />}>
          <Route path="ai/datasets" element={<DatasetsPage />} />
          <Route path="ai/datasets/:datasetId" element={<DatasetDetailPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}
const detail = (role: Role) => page(role, '/w/w1/ai/datasets/d1')
const openTab = (name: string) => userEvent.click(screen.getByRole('tab', { name }))

beforeEach(() => {
  state.sampleParams = []
  state.q = {
    policy: ok({ eligible: ['CC0-1.0', 'CC-BY-4.0'], excluded: ['CC BY-SA (any version)'], not_covered: 'other licences cannot be approved here', override: 'none: an exception is a recorded owner decision', status: 'CC0 and CC BY are accepted provisionally, subject to verification', approval_requires: ['an https source URL'], download_rule: 'a dataset must not be downloaded unless its status is approved' }),
    list: ok({ items: [], total: 0, limit: 200, offset: 0 }),
    dataset: ok(dataset()),
    samples: ok({ items: [], total: 0, limit: 25, offset: 0 }),
    reviews: ok([]),
    summary: ok({ by_status: {}, reviewed_fraction: 0, qualified_reviewers_verified: 0, note: '' }),
    quality: ok({ samples: 0, passed: false, issues: [] }),
    agreement: ok({ samples_with_a_decision: 0, samples_with_two_reviewers: 0, reviewers: 0, observed_agreement: null, cohens_kappa: null, disagreements: [], caveats: ['reviewers are not verified as qualified'] }),
    splits: ok([]),
    claims: ok({ allowed: false, blockers: [], split_version: null, note: 'Engineering gate.' }),
  }
  state.mut = { create: idle(), evidence: idle(), transition: idle(), review: idle(), split: idle() }
})

describe('datasets catalog', () => {
  it('shows loading, error, permission-denied and empty states', () => {
    state.q.list = { isLoading: true, error: null, data: undefined, refetch: vi.fn() }
    const a = page('viewer')
    expect(screen.getByText(/loading datasets/i)).toBeInTheDocument()
    a.unmount()
    state.q.list = { isLoading: false, error: new Error('boom'), data: undefined, refetch: vi.fn() }
    const b = page('viewer')
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
    b.unmount()
    state.q.list = { isLoading: false, error: new ProblemError(403, 'insufficient_role', 'Not allowed'), data: undefined, refetch: vi.fn() }
    const c = page('viewer')
    expect(screen.getByText('You do not have access to this')).toBeInTheDocument()
    c.unmount()
    state.q.list = ok({ items: [], total: 0, limit: 200, offset: 0 })
    page('viewer')
    expect(screen.getByText('No datasets in the catalog')).toBeInTheDocument()
  })

  it('keeps candidates and approved datasets apart and groups versions under one name', () => {
    state.q.list = ok({ total: 3, limit: 200, offset: 0, items: [
      item({ id: 'a', name: 'Approved set', status: 'approved', blockers: [], image_origin: 'publisher_created', approved_by: 'u1' }),
      item({ id: 'b', version: '2', status: 'proposed' }),
      item({ id: 'c', name: 'Other set', status: 'rejected', licence_spdx: 'CC-BY-SA-3.0', licence_verdict: 'excluded' }),
    ] })
    page('viewer')
    const approved = screen.getByRole('region', { name: 'Approved datasets' })
    const candidates = screen.getByRole('region', { name: 'Candidates (not approved)' })
    expect(within(approved).getByText('Approved set')).toBeInTheDocument()
    expect(within(approved).queryByText('Version 2')).not.toBeInTheDocument()
    expect(within(approved).queryByText('Other set')).not.toBeInTheDocument()
    expect(within(candidates).queryByText('Approved set')).not.toBeInTheDocument() // an approved dataset is never listed as a candidate
    expect(within(candidates).getByText('Version 2')).toBeInTheDocument()
    expect(within(candidates).getByText('Other set')).toBeInTheDocument()
    expect(within(candidates).getByText('Rejected')).toBeInTheDocument()
    expect(within(candidates).getByText('Licence excluded by policy')).toBeInTheDocument()
    expect(within(candidates).getAllByText(/1 open blocker/).length).toBeGreaterThan(0)
    expect(screen.getByText(/never downloads datasets/i)).toBeInTheDocument()
  })

  it('states the licence policy and that there is no override', async () => {
    page('viewer')
    await userEvent.click(screen.getByText(/Licence policy and what an approval requires/))
    expect(screen.getByText(/Override: none/)).toBeInTheDocument()
    expect(screen.getByText(/must not be downloaded unless its status is approved/)).toBeInTheDocument()
  })

  it('offers the proposal form only to managers, and submits what was entered', async () => {
    const v = page('viewer')
    expect(screen.queryByRole('button', { name: 'Propose a dataset' })).not.toBeInTheDocument()
    v.unmount()
    page('manager')
    await userEvent.click(screen.getByRole('button', { name: 'Propose a dataset' }))
    await userEvent.type(screen.getByLabelText('Name'), 'My set')
    await userEvent.type(screen.getByLabelText('Version'), '1')
    await userEvent.type(screen.getByLabelText('Official source (https)'), 'https://x.example.org')
    await userEvent.type(screen.getByLabelText(/Licence \(SPDX/), 'CC0-1.0')
    await userEvent.click(screen.getByRole('button', { name: 'Propose dataset' }))
    const body = state.mut.create.mutate.mock.calls[0][0] as Record<string, unknown>
    expect(body).toMatchObject({ name: 'My set', kind: 'real', licence_spdx: 'CC0-1.0', image_origin: 'unknown', commercial_use: 'unknown' })
    expect(body).not.toHaveProperty('status') // a client cannot propose an approved dataset
  })

  it('shows a refusal from the server when a proposal is rejected', async () => {
    state.mut.create.error = new ProblemError(409, 'dataset_exists', 'dataset already exists')
    page('manager')
    await userEvent.click(screen.getByRole('button', { name: 'Propose a dataset' }))
    expect(screen.getByRole('alert')).toHaveTextContent('already exists')
  })
})

describe('dataset detail: licence, evidence and approval', () => {
  it('presents a candidate as not approved, lists the blockers and explains the image origin', () => {
    detail('viewer')
    expect(screen.getByText(/Candidate, not approved/)).toBeInTheDocument()
    expect(screen.getByText(/Do not download it/)).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Approval blockers' })).toHaveTextContent('1 open blocker')
    expect(within(screen.getByRole('group', { name: 'Approval blockers' })).getByRole('listitem')).toHaveTextContent(/image origin is 'unknown'/) // the server's reason is shown, not just a count
    expect(screen.getByText(/Who made the images, and with what permission, is not established/)).toBeInTheDocument()
    expect(screen.getByText('Licence eligible (provisional)')).toBeInTheDocument()
    expect(screen.getByText('No evidence has been recorded. Nothing here is verified.')).toBeInTheDocument()
  })

  it('shows evidence with its quoted statement, whether the source is official, and a safe link', () => {
    state.q.dataset = ok(dataset({ evidence: [
      { id: 'e1', url: 'https://data.example.org/LICENSE', kind: 'licence_page', scope: 'images', licence_spdx: 'CC-BY-4.0', excerpt: 'Released under the Creative Commons Attribution 4.0 licence [verified: read_in_full_text]', official: true, accessed_at: '2026-10-18T00:00:00Z', recorded_by: 'user-bbbb', recorded_at: '2026-10-18T00:00:00Z' },
      { id: 'e2', url: 'javascript:alert(1)', kind: 'other', scope: 'both', licence_spdx: 'CC0-1.0', excerpt: 'A mirror says CC0', official: false, accessed_at: '2026-10-18T00:00:00Z', recorded_by: null, recorded_at: '2026-10-18T00:00:00Z' },
    ] }))
    detail('viewer')
    expect(screen.getByText('Official source')).toBeInTheDocument()
    expect(screen.getByText('Not an official source')).toBeInTheDocument()
    expect(screen.getByText(/Released under the Creative Commons Attribution 4.0 licence \[verified: read_in_full_text\]/).tagName).toBe('BLOCKQUOTE')
    expect(screen.getByRole('link', { name: 'https://data.example.org/LICENSE' })).toHaveAttribute('rel', 'noreferrer noopener')
    expect(screen.queryByRole('link', { name: /javascript/ })).not.toBeInTheDocument() // only https is ever a link
  })

  it('shows scraped images as a critical status', () => {
    state.q.dataset = ok(dataset({ image_origin: 'third_party_scraped' }))
    detail('viewer')
    expect(screen.getAllByText('Images scraped from third parties').length).toBeGreaterThan(0)
    expect(screen.getByText(/cannot be approved without written confirmation/)).toBeInTheDocument()
  })

  it('gives viewers and workers no workflow buttons, and managers no approval button', () => {
    const v = detail('viewer')
    expect(screen.queryByRole('button', { name: /Approve|Reject|Start review/ })).not.toBeInTheDocument()
    expect(screen.getByText(/Only managers can move a dataset through review/)).toBeInTheDocument()
    v.unmount()
    detail('manager')
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.getByText(/An owner or admin makes the approval decision/)).toBeInTheDocument()
    expect(screen.getByRole('form', { name: 'Record licence evidence' })).toBeInTheDocument()
  })

  it('offers approval to admins but lets the server decide, and shows the blockers it returns', async () => {
    state.mut.transition.error = new ProblemError(422, 'dataset_not_approvable', 'The dataset cannot be approved yet', [], {
      body: { blockers: ['no official-source evidence with a quoted licence statement covers the images'] },
    })
    detail('admin')
    expect(screen.getByText(/The server will refuse approval while blockers remain/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(state.mut.transition.mutate).toHaveBeenCalledWith({ to_status: 'approved', note: undefined })
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('cannot be approved yet')
    expect(alert).toHaveTextContent('no official-source evidence')
  })

  it('shows a 403 from the server on a decision', () => {
    state.mut.transition.error = new ProblemError(403, 'insufficient_role', 'Requires role admin or higher')
    detail('admin')
    expect(screen.getByRole('alert')).toHaveTextContent('Requires role admin')
  })

  it('submits evidence as an ISO date with the quoted statement, for managers on open datasets only', async () => {
    detail('manager')
    await userEvent.type(screen.getByLabelText('Source address (https)'), 'https://data.example.org/licence')
    await userEvent.type(screen.getByLabelText(/Licence this source states/), 'CC-BY-4.0')
    await userEvent.type(screen.getByLabelText('Date you read it'), '2026-10-18')
    await userEvent.type(screen.getByLabelText(/Quoted licence statement/), 'Released under CC BY 4.0')
    await userEvent.click(screen.getByLabelText(/Official source \(the publisher/))
    await userEvent.click(screen.getByRole('button', { name: 'Record evidence' }))
    expect(state.mut.evidence.mutate.mock.calls[0][0]).toMatchObject({ url: 'https://data.example.org/licence', licence_spdx: 'CC-BY-4.0', official: true, scope: 'images', accessed_at: '2026-10-18T00:00:00.000Z' })
  })

  it('treats an approved dataset as approved without claiming more, and lets managers re-open it', () => {
    state.q.dataset = ok(dataset({ status: 'approved', blockers: [], image_origin: 'publisher_created', approved_by: 'owner-1234', approved_at: '2026-10-18T10:00:00Z', download_allowed: true }))
    detail('manager')
    expect(screen.getAllByText('Approved').length).toBeGreaterThan(0)
    expect(screen.getByText(/not a statement that the data is good enough to train or evaluate a model/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Re-open for review/ })).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Record licence evidence' })).not.toBeInTheDocument()
  })

  it('treats rejection as final', () => {
    state.q.dataset = ok(dataset({ status: 'rejected' }))
    detail('admin')
    expect(screen.getByText(/Rejected datasets are final/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
  })

  it('labels a synthetic fixture as not biological data and offers no approval', () => {
    state.q.dataset = ok(dataset({ kind: 'synthetic', is_biological_data: false, licence_spdx: 'SYNTHETIC', licence_verdict: 'not_applicable', blockers: [] }))
    detail('admin')
    expect(screen.getAllByText(/not biological data/i).length).toBeGreaterThan(0)
    expect(screen.getByText('Synthetic fixtures need no approval.')).toBeInTheDocument()
  })

  it('shows loading, error and permission-denied states for the dataset', () => {
    state.q.dataset = { isLoading: true, error: null, data: undefined, refetch: vi.fn() }
    const a = detail('viewer')
    expect(screen.getByText(/loading dataset/i)).toBeInTheDocument()
    a.unmount()
    state.q.dataset = { isLoading: false, error: new ProblemError(404, 'dataset_not_found', 'Dataset not found'), data: undefined, refetch: vi.fn() }
    detail('viewer')
    expect(screen.getByRole('alert')).toHaveTextContent('Dataset not found')
  })
})

describe('dataset detail: samples and label review', () => {
  beforeEach(() => {
    state.q.dataset = ok(dataset({ kind: 'synthetic', is_biological_data: false, status: 'proposed', blockers: [] }))
  })

  it('says that reviewers are unverified and that no label is expert validation', async () => {
    state.q.summary = ok({ by_status: { unreviewed: 3, accepted: 1 }, reviewed_fraction: 0.25, qualified_reviewers_verified: 0, note: '' })
    state.q.samples = ok({ items: [sample(), sample({ id: 's2', external_id: 'item-0002', label_status: 'accepted' })], total: 2, limit: 25, offset: 0 })
    detail('viewer')
    await openTab('Samples and review')
    expect(screen.getByText(/Reviewers are not verified as qualified/)).toBeInTheDocument()
    expect(screen.getByText('Verified qualified reviewers: 0')).toBeInTheDocument()
    expect(within(screen.getAllByRole('list').at(-1) as HTMLElement).getByText('Accepted')).toBeInTheDocument()
    expect(screen.queryByText(/expert[- ]validated/i)).not.toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/\bvalidated by (an )?expert/i)
  })

  it('shows an empty state, and an honest one for real datasets that are not approved', async () => {
    detail('viewer')
    await openTab('Samples and review')
    expect(screen.getByText('No samples are registered')).toBeInTheDocument()
  })

  it('filters by label status through the server', async () => {
    state.q.samples = ok({ items: [sample()], total: 1, limit: 25, offset: 0 })
    detail('viewer')
    await openTab('Samples and review')
    await userEvent.selectOptions(screen.getByLabelText('Show labels that are'), 'accepted')
    expect(state.sampleParams[state.sampleParams.length - 1]).toMatchObject({ label_status: 'accepted' })
  })

  it('gives viewers the history but no review controls', async () => {
    state.q.samples = ok({ items: [sample({ label_status: 'under_review' })], total: 1, limit: 25, offset: 0 })
    state.q.reviews = ok([{ id: 'r1', sample_id: 's1', reviewer_id: 'reviewer-aaaa', reviewer_qualification: 'agronomy student', qualification_verified: false, from_status: 'unreviewed', to_status: 'under_review', from_label: 'blight', to_label: 'blight', evidence: null, at: '2026-10-18T10:00:00Z' }])
    detail('viewer')
    await openTab('Samples and review')
    await userEvent.click(screen.getByRole('button', { name: 'Review and history' }))
    expect(screen.getByText(/Declared qualification: “agronomy student”/)).toHaveTextContent('unverified')
    expect(screen.getByText(/Only managers can review labels/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Accept label' })).not.toBeInTheDocument()
  })

  it('requires written evidence before a decision and a new label before a correction', async () => {
    state.q.samples = ok({ items: [sample({ label_status: 'under_review' })], total: 1, limit: 25, offset: 0 })
    detail('manager')
    await openTab('Samples and review')
    await userEvent.click(screen.getByRole('button', { name: 'Review and history' }))
    const accept = screen.getByRole('button', { name: 'Accept label' })
    expect(accept).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Correct label' })).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/Evidence for your decision/), 'Compared with the source record')
    expect(accept).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Correct label' })).toBeDisabled() // still needs a new label
    await userEvent.type(screen.getByLabelText(/New label/), 'rust')
    expect(screen.getByRole('button', { name: 'Correct label' })).toBeEnabled()
    await userEvent.type(screen.getByLabelText(/Your qualification/), 'self-taught grower')
    await userEvent.click(accept)
    expect(state.mut.review.mutate.mock.calls[0][0]).toMatchObject({
      sampleId: 's1', body: { to_status: 'accepted', evidence: 'Compared with the source record', reviewer_qualification: 'self-taught grower' },
    })
    expect(screen.getByLabelText(/Your qualification/).closest('div')).toHaveTextContent('does not verify it')
  })

  it('never lets the client name the reviewer', async () => {
    state.q.samples = ok({ items: [sample()], total: 1, limit: 25, offset: 0 })
    detail('manager')
    await openTab('Samples and review')
    await userEvent.click(screen.getByRole('button', { name: 'Review and history' }))
    await userEvent.click(screen.getByRole('button', { name: 'Start review' }))
    const body = (state.mut.review.mutate.mock.calls[0][0] as { body: Record<string, unknown> }).body
    expect(body).toEqual({ to_status: 'under_review', evidence: undefined, reviewer_qualification: undefined })
    expect(Object.keys(body).some((k) => /reviewer_id|reviewer$|name/.test(k))).toBe(false)
  })

  it('shows a refusal from the server on a review', async () => {
    state.mut.review.error = new ProblemError(409, 'invalid_review', 'a decision needs written evidence')
    state.q.samples = ok({ items: [sample({ label_status: 'accepted' })], total: 1, limit: 25, offset: 0 })
    detail('manager')
    await openTab('Samples and review')
    await userEvent.click(screen.getByRole('button', { name: 'Review and history' }))
    expect(screen.getByRole('alert')).toHaveTextContent('a decision needs written evidence')
    expect(screen.getByRole('button', { name: 'Re-open' })).toBeInTheDocument()
  })
})

describe('dataset detail: quality, splits, agreement and claims', () => {
  it('reports quality problems, and says so when there is nothing to check', async () => {
    const first = detail('viewer')
    await openTab('Quality')
    expect(screen.getByText('No samples to check')).toBeInTheDocument()
    first.unmount()
    state.q.quality = ok({ samples: 40, passed: false, reviewed_fraction: 0, label_status: {}, groups: { count: 4, largest: 12 },
      classes: { classes: 2, counts: { a: 30, b: 10 }, max_over_min: 3 },
      issues: [{ code: 'exact_duplicates', severity: 'error', message: 'byte-identical files', count: 2, examples: ['s1', 's2'] }, { code: 'no_reviewed_labels', severity: 'warning', message: 'no label has been reviewed', count: 0, examples: [] }] })
    state.q.dataset = ok(dataset())
    const again = detail('viewer')
    await openTab('Quality')
    expect(screen.getAllByText('Has error-level issues').length).toBeGreaterThan(0)
    expect(screen.getByText('exact_duplicates')).toBeInTheDocument()
    expect(screen.getByText(/Passing them does not make labels correct/)).toBeInTheDocument()
    again.unmount()
  })

  it('shows split versions with leakage status, warnings and no fabricated numbers', async () => {
    state.q.splits = ok([{ id: 'sp1', version: 2, seed: 7, fractions: {}, include_unreviewed: true, manifest_sha256: 'a'.repeat(64), warnings: ['split \'test\' has only 2 group(s)'], leakage_violations: [],
      stats: { train: { items: 70, target_fraction: 0.7, actual_fraction: 0.7, groups: 10, labels: {} } }, created_by: null, created_at: '2026-10-18T10:00:00Z' }])
    detail('viewer')
    await openTab('Splits')
    expect(screen.getByText('Version 2')).toBeInTheDocument()
    expect(screen.getByText('Includes unreviewed labels')).toBeInTheDocument()
    expect(screen.getByText('No leakage found by the checker')).toBeInTheDocument()
    expect(screen.getByText(/has only 2 group/)).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Create a split' })).not.toBeInTheDocument() // managers only
  })

  it('creates a split for managers and shows the server refusal', async () => {
    state.mut.split.error = new ProblemError(422, 'split_impossible', '1 group(s) cannot fill 3 splits')
    detail('manager')
    await openTab('Splits')
    expect(screen.getByText('No split yet')).toBeInTheDocument()
    await userEvent.click(screen.getByLabelText(/Include labels that are not reviewed/))
    await userEvent.click(screen.getByRole('button', { name: /Create split/ }))
    expect(state.mut.split.mutate).toHaveBeenCalledWith({ seed: 0, include_unreviewed: true })
    expect(screen.getByRole('alert')).toHaveTextContent('cannot fill 3 splits')
  })

  it('shows Cohen’s kappa only when computed, and with its caveats', async () => {
    detail('viewer')
    await openTab('Reviewer agreement')
    expect(screen.getByText('not computed')).toBeInTheDocument()
    expect(screen.getByText('not available')).toBeInTheDocument()
    expect(screen.getAllByText(/not verified as qualified/).length).toBeGreaterThan(0)
  })

  it('shows measured agreement and the disagreements', async () => {
    state.q.agreement = ok({ samples_with_a_decision: 5, samples_with_two_reviewers: 4, reviewers: 2, observed_agreement: 0.75, cohens_kappa: 0.4, caveats: ['agreement measures consistency, not correctness'], disagreements: [{ sample_id: 'abcdef1234', verdicts: ['a', 'b'] }] })
    detail('viewer')
    await openTab('Reviewer agreement')
    expect(screen.getByText('0.40')).toBeInTheDocument()
    expect(screen.getByText('75%')).toBeInTheDocument()
    expect(screen.getByText(/consistency, not correctness/)).toBeInTheDocument()
    expect(screen.getByText(/abcdef12: a vs b/)).toBeInTheDocument()
  })

  it('keeps performance claims blocked and flags the blockers the application cannot clear', async () => {
    state.q.claims = ok({ allowed: false, split_version: 1, note: 'Engineering gate.', blockers: [
      { code: 'synthetic_data', message: 'synthetic fixtures are not biological data', resolvable_in_application: false },
      { code: 'labels_not_reviewed', message: 'only 10% of labels are reviewed', resolvable_in_application: true },
    ] })
    detail('viewer')
    await openTab('Claim gate')
    expect(screen.getByText('Performance claims are blocked')).toBeInTheDocument()
    const list = screen.getByRole('list', { name: 'Claim blockers' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(2)
    expect(within(list).getAllByText('Cannot be cleared inside this application')).toHaveLength(1)
  })

  it('never calls an empty blocker list proof of quality', async () => {
    state.q.claims = ok({ allowed: true, split_version: 1, note: 'Engineering gate.', blockers: [] })
    detail('viewer')
    await openTab('Claim gate')
    expect(screen.getByText(/this is not proof of quality/)).toBeInTheDocument()
    expect(screen.queryByText(/approved for/i)).not.toBeInTheDocument()
  })

  it('shows loading and permission-denied states on a tab', async () => {
    state.q.claims = { isLoading: true, error: null, data: undefined, refetch: vi.fn() }
    const a = detail('viewer')
    await openTab('Claim gate')
    expect(screen.getByText(/loading claim readiness/i)).toBeInTheDocument()
    a.unmount()
    state.q.claims = { isLoading: false, error: new ProblemError(403, 'insufficient_role', 'no'), data: undefined, refetch: vi.fn() }
    detail('viewer')
    await openTab('Claim gate')
    expect(screen.getByText('You do not have access to this')).toBeInTheDocument()
  })
})
