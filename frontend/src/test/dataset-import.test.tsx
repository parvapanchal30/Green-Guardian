import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ProblemError } from '../api/client'
import type { DatasetDetailRecord, ImportReport, Role } from '../api/types'

type Mut = { mutate: ReturnType<typeof vi.fn>; isPending: boolean; error: unknown; isSuccess?: boolean; data?: unknown }
const idle = (): Mut => ({ mutate: vi.fn(), isPending: false, error: null })
const state = vi.hoisted(() => ({ imp: {} as Mut, reg: {} as Mut }))

vi.mock('../lib/datasets', () => ({
  useImportSamples: () => state.imp,
  useRegisterSample: () => state.reg,
  useDatasetSamples: () => ({ isLoading: false, error: null, data: { items: [], total: 0, limit: 25, offset: 0 }, refetch: vi.fn() }),
  useReviewSummary: () => ({ isLoading: false, error: null, data: { by_status: {}, reviewed_fraction: 0, qualified_reviewers_verified: 0, note: '' } }),
  useSampleReviews: () => ({ isLoading: false, error: null, data: [] }),
  useReviewSample: () => idle(),
}))

import { ImportPanel } from '../components/datasets/ImportPanel'
import { SamplesTab } from '../components/datasets/SamplesTab'

const dataset = (over: Partial<DatasetDetailRecord> = {}): DatasetDetailRecord => ({
  id: 'd1', name: 'Fixtures', version: '1', kind: 'synthetic', source_url: 'synthetic://generated', accessed_at: null, licence_spdx: 'SYNTHETIC',
  images_licence_spdx: 'SYNTHETIC', annotations_licence_spdx: null, has_annotations: false, image_origin: 'unknown', attribution_required: null,
  attribution_text: null, commercial_use: 'unknown', redistribution: 'unknown', intended_use: '', notes: null, status: 'proposed', created_by: null,
  created_at: '2026-10-18T00:00:00Z', approved_by: null, approved_at: null, licence_verdict: 'not_applicable', blockers: [], download_allowed: false,
  is_biological_data: false, evidence: [], history: [], sample_count: 0, ...over,
})
const report = (over: Partial<ImportReport> = {}): ImportReport => ({
  status: 'preview', ok: true, csv_sha256: 'a'.repeat(64), columns: ['external_id', 'source'], rows_total: 3, rows_with_errors: 0, to_create: 3, unchanged: 0,
  error_count: 0, errors: [], errors_truncated: false, warnings: [], label_status_after_import: 'unreviewed',
  note: 'Imported labels are unreviewed. They count as validated only after a recorded review.', ...over,
})
const csv = (name = 'samples.csv', body = 'external_id,source\na,s\nb,s\nc,s\n') => new File([body], name, { type: 'text/csv' })

function panel(d: DatasetDetailRecord = dataset()) {
  return render(<ImportPanel ws="w1" d={d} />)
}
async function choose(file: File, applyAccept = true) {
  // applyAccept=false simulates a browser that lets the person pick any file despite the accept hint
  await userEvent.setup({ applyAccept }).upload(screen.getByLabelText('CSV file'), file)
}
/** Run the mutation's onSuccess/onError callbacks as the real hook would. */
const resolveWith = (m: Mut, r: ImportReport) => m.mutate.mockImplementation((_b, o) => o?.onSuccess?.(r))
const rejectWith = (m: Mut, e: unknown) => m.mutate.mockImplementation((_b, o) => o?.onError?.(e))

beforeEach(() => {
  state.imp = idle()
  state.reg = idle()
})

describe('CSV import panel', () => {
  it('states that every imported label starts unreviewed and review status cannot be imported', () => {
    panel()
    expect(screen.getByText(/Every imported label starts unreviewed/)).toBeInTheDocument()
    expect(screen.getByText(/A column that tries to carry review status is refused/)).toBeInTheDocument()
  })

  it('does not offer import for a real dataset that is not approved', () => {
    panel(dataset({ kind: 'real', status: 'under_review' }))
    expect(screen.getByText(/can only be registered once it is approved/)).toBeInTheDocument()
    expect(screen.queryByLabelText('CSV file')).not.toBeInTheDocument()
  })

  it('rejects the wrong kind of file and oversized files before anything is sent', async () => {
    panel()
    await choose(new File(['x'], 'notes.txt', { type: 'text/plain' }), false)
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a .csv file')
    expect(screen.getByRole('button', { name: /Preview/ })).toBeDisabled()
    await choose(new File([new Uint8Array(2_000_001)], 'big.csv', { type: 'text/csv' }), false)
    expect(screen.getByRole('alert')).toHaveTextContent('larger than 2 MB')
    expect(state.imp.mutate).not.toHaveBeenCalled()
  })

  it('previews through the server without writing, and only then offers the import', async () => {
    resolveWith(state.imp, report())
    panel()
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled()
    await choose(csv())
    await waitFor(() => expect(screen.getByText(/3 data rows read in the browser/)).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: /Preview/ }))
    expect(state.imp.mutate.mock.calls[0][0]).toEqual({ csv_text: 'external_id,source\na,s\nb,s\nc,s\n', commit: false })
    expect(await screen.findByRole('button', { name: 'Import 3 samples' })).toBeEnabled()
    expect(screen.getByLabelText('Import report')).toHaveTextContent('3 to create')
  })

  it('imports exactly the previewed text and reports the outcome', async () => {
    resolveWith(state.imp, report())
    panel()
    await choose(csv())
    await userEvent.click(await screen.findByRole('button', { name: /Preview/ }))
    resolveWith(state.imp, report({ status: 'imported' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Import 3 samples' }))
    expect(state.imp.mutate.mock.calls[1][0]).toEqual({ csv_text: 'external_id,source\na,s\nb,s\nc,s\n', commit: true })
    expect(await screen.findByRole('status')).toHaveTextContent('Imported 3 samples as unreviewed')
  })

  it('shows row-level errors and keeps the import disabled', async () => {
    resolveWith(state.imp, report({
      ok: false, to_create: 0, error_count: 2, rows_with_errors: 2,
      errors: [
        { row: 2, external_id: 'b', column: 'content_sha256', code: 'invalid_value', message: 'must be 64 lower-case hexadecimal characters (SHA-256)' },
        { row: 3, external_id: 'c', column: 'source', code: 'missing_provenance', message: 'source is empty: every sample needs a recorded origin' },
      ],
    }))
    panel()
    await choose(csv())
    await userEvent.click(await screen.findByRole('button', { name: /Preview/ }))
    const table = await screen.findByRole('table', { name: 'Import errors' })
    expect(within(table).getAllByRole('row')).toHaveLength(3)
    expect(within(table).getByText('content_sha256')).toBeInTheDocument()
    expect(within(table).getByText(/every sample needs a recorded origin/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled()
    expect(screen.getByText(/a file with any error imports nothing/)).toBeInTheDocument()
  })

  it('never enables the import for a report that is not ok, even if it claims rows to create', async () => {
    resolveWith(state.imp, report({ ok: false, to_create: 3, error_count: 1, errors: [{ row: 1, code: 'invalid_value', message: 'bad', external_id: 'a', column: 'phash' }] }))
    panel()
    await choose(csv())
    await userEvent.click(await screen.findByRole('button', { name: /Preview/ }))
    expect(await screen.findByRole('table', { name: 'Import errors' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled()
  })

  it('shows file-level problems such as a forbidden review column', async () => {
    resolveWith(state.imp, report({ ok: false, to_create: 0, error_count: 1, rows_total: 0, errors: [{ row: null, code: 'review_state_not_importable', message: 'column(s) label_status cannot be imported: every imported label starts as unreviewed' }] }))
    panel()
    await choose(csv('x.csv', 'external_id,source,label_status\na,s,accepted\n'))
    await userEvent.click(await screen.findByRole('button', { name: /Preview/ }))
    expect(await screen.findByText(/label_status cannot be imported/)).toBeInTheDocument()
  })

  it('truncates a long error list and says how many there are', async () => {
    const errors = Array.from({ length: 80 }, (_, i) => ({ row: i + 1, external_id: `s${i}`, column: 'phash', code: 'invalid_value', message: 'bad' }))
    resolveWith(state.imp, report({ ok: false, to_create: 0, error_count: 300, errors, errors_truncated: true }))
    panel()
    await choose(csv())
    await userEvent.click(await screen.findByRole('button', { name: /Preview/ }))
    const table = await screen.findByRole('table', { name: 'Import errors' })
    expect(within(table).getAllByRole('row')).toHaveLength(51)
    expect(screen.getByText('Showing the first 50 of 300 errors.')).toBeInTheDocument()
  })

  it('lists aggregated warnings without blocking the import', async () => {
    resolveWith(state.imp, report({ warnings: [{ code: 'missing_group', message: 'rows without a group_key cannot be kept apart in a grouped split', count: 2, rows: [1, 3] }] }))
    panel()
    await choose(csv())
    await userEvent.click(await screen.findByRole('button', { name: /Preview/ }))
    expect(await screen.findByLabelText('Import warnings')).toHaveTextContent('2 rows')
    expect(screen.getByRole('button', { name: 'Import 3 samples' })).toBeEnabled()
  })

  it('shows the server report when a commit is refused, and a retried file as already imported', async () => {
    resolveWith(state.imp, report())
    panel()
    await choose(csv())
    await userEvent.click(await screen.findByRole('button', { name: /Preview/ }))
    const refused = report({ ok: false, to_create: 0, error_count: 1, errors: [{ row: 1, external_id: 'a', code: 'exists_with_different_values', message: 'already registered with different label; imports never overwrite a sample' }] })
    rejectWith(state.imp, new ProblemError(422, 'import_invalid', 'The file has errors; nothing was imported', [], { body: { report: refused } }))
    await userEvent.click(await screen.findByRole('button', { name: 'Import 3 samples' }))
    expect(await screen.findByText(/imports never overwrite a sample/)).toBeInTheDocument()
    resolveWith(state.imp, report({ status: 'already_imported', to_create: 0, unchanged: 3 }))
    await userEvent.click(screen.getByRole('button', { name: /Preview/ }))
    expect(await screen.findByRole('button', { name: 'Import' })).toBeDisabled() // nothing new to import
  })

  it('shows a plain error when the request itself fails', async () => {
    state.imp.error = new ProblemError(403, 'insufficient_role', 'Requires role manager or higher')
    panel()
    expect(screen.getByRole('alert')).toHaveTextContent('Requires role manager')
  })

  it('registers a single sample as unreviewed and requires a source for real datasets', async () => {
    panel(dataset({ kind: 'real', status: 'approved' }))
    await userEvent.click(screen.getByText('Register a single sample'))
    expect(screen.getByLabelText('Source (where it came from)')).toBeRequired()
    await userEvent.type(screen.getByLabelText('Sample identifier'), 'one-1')
    await userEvent.type(screen.getByLabelText('Source (where it came from)'), 'field visit 3')
    await userEvent.click(screen.getByRole('button', { name: 'Register sample' }))
    expect(state.reg.mutate.mock.calls[0][0]).toEqual({ samples: [{ external_id: 'one-1', group_key: undefined, label: undefined, provenance: { source: 'field visit 3' } }] })
    const body = (state.reg.mutate.mock.calls[0][0] as { samples: Record<string, unknown>[] }).samples[0]
    expect(Object.keys(body)).not.toContain('label_status') // review state is not something a client can set
  })
})

describe('import in the samples tab', () => {
  const tab = (role: Role) => {
    const ctx = { ws: 'w1', workspace: { id: 'w1', name: 'City', mode: 'green_management', role }, capabilities: [] }
    return render(
      <MemoryRouter initialEntries={['/x']}>
        <Routes><Route path="/" element={<Outlet context={ctx} />}><Route path="x" element={<SamplesTab ws="w1" d={dataset()} role={role} />} /></Route></Routes>
      </MemoryRouter>,
    )
  }
  it('is offered to managers and not to viewers or workers', () => {
    const a = tab('manager')
    expect(screen.getByLabelText('CSV file')).toBeInTheDocument()
    a.unmount()
    for (const role of ['viewer', 'worker'] as Role[]) {
      const x = tab(role)
      expect(screen.queryByLabelText('CSV file')).not.toBeInTheDocument()
      expect(screen.getByText('Only managers can add samples.')).toBeInTheDocument()
      x.unmount()
    }
  })
})
