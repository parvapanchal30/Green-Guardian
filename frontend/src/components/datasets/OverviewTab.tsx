import { useState, type FormEvent } from 'react'
import { ProblemError } from '../../api/client'
import type { DatasetDetailRecord } from '../../api/types'
import { atLeast, fmtDate, fmtDateTime, label } from '../../lib/format'
import { useAddEvidence, useTransitionDataset } from '../../lib/datasets'
import type { Role } from '../../api/types'
import { Field, btn, btnPrimary, input } from '../domain'
import { errorMessage } from '../states'
import { StatusChip } from '../StatusChip'
import { DatasetStatusChip, Fact, LicenceVerdictChip, OriginChip, SafeUrl, isApproved, originExplanation, short } from './shared'

const EVIDENCE_KINDS = ['licence_page', 'readme', 'paper', 'repository', 'archive_record', 'data_card', 'other']

/** Blockers the server reported in a refused request (422 dataset_not_approvable), if any. */
export function blockersFrom(error: unknown): string[] {
  if (error instanceof ProblemError && Array.isArray(error.body.blockers)) return error.body.blockers.map(String)
  return []
}

function Blockers({ d }: { d: DatasetDetailRecord }) {
  if (d.kind === 'synthetic') return <p className="text-sm text-ink-2">Synthetic fixtures have no external licence and are never biological data.</p>
  if (isApproved(d)) return <p className="text-sm text-ink-2">No open blockers: every approval requirement is currently met.</p>
  if (d.blockers.length === 0) return <p className="text-sm text-ink-2">No open blockers reported by the server.</p>
  return (
    <div role="group" aria-label="Approval blockers" className="rounded border border-at-risk p-3">
      <p className="text-sm font-medium">{d.blockers.length} open blocker{d.blockers.length === 1 ? '' : 's'}: this dataset cannot be approved until each is resolved with evidence.</p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-2">{d.blockers.map((b) => <li key={b}>{b}</li>)}</ul>
    </div>
  )
}

function Workflow({ ws, d, role }: { ws: string; d: DatasetDetailRecord; role: Role }) {
  const move = useTransitionDataset(ws, d.id)
  const [note, setNote] = useState('')
  const canReview = atLeast(role, 'manager')
  const canDecide = atLeast(role, 'admin')
  if (!canReview) return <p className="text-sm text-ink-3">Only managers can move a dataset through review; only owners and admins can approve or reject it.</p>
  if (d.status === 'rejected') return <p className="text-sm text-ink-2">Rejected datasets are final. A corrected description is entered as a new version.</p>
  const refused = blockersFrom(move.error)
  const go = (to: string) => move.mutate({ to_status: to, note: note.trim() || undefined })
  return (
    <div className="space-y-2">
      <Field id="dataset-note" label="Note (optional)"><input id="dataset-note" className={input} value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} /></Field>
      <div className="flex flex-wrap gap-2">
        {(d.status === 'proposed' || d.status === 'approved') && (
          <button type="button" className={btn} disabled={move.isPending} onClick={() => go('under_review')}>
            {d.status === 'approved' ? 'Re-open for review (clears approval)' : 'Start review'}
          </button>
        )}
        {d.status === 'under_review' && canDecide && (
          <button type="button" className={btnPrimary} disabled={move.isPending} onClick={() => go('approved')}>Approve</button>
        )}
        {canDecide && <button type="button" className={btn} disabled={move.isPending} onClick={() => go('rejected')}>Reject</button>}
      </div>
      {d.status === 'under_review' && !canDecide && <p className="text-xs text-ink-3">An owner or admin makes the approval decision.</p>}
      {d.status === 'under_review' && canDecide && d.blockers.length > 0 && (
        <p className="text-xs text-ink-3">The server will refuse approval while blockers remain; this page does not check them for it.</p>
      )}
      {move.error != null && (
        <div role="alert" className="rounded border border-critical p-2 text-sm">
          <p className="text-critical">{errorMessage(move.error)}</p>
          {refused.length > 0 && <ul className="mt-1 list-disc pl-5 text-ink-2">{refused.map((b) => <li key={b}>{b}</li>)}</ul>}
        </div>
      )}
    </div>
  )
}

function EvidenceForm({ ws, d }: { ws: string; d: DatasetDetailRecord }) {
  const add = useAddEvidence(ws, d.id)
  const blank = { url: '', kind: 'licence_page', scope: 'images', licence_spdx: '', excerpt: '', official: false, accessed_at: '' }
  const [f, setF] = useState(blank)
  const set = (k: keyof typeof blank, v: string | boolean) => setF((s) => ({ ...s, [k]: v }))
  const submit = (e: FormEvent) => {
    e.preventDefault()
    add.mutate({ ...f, licence_spdx: f.licence_spdx.trim(), accessed_at: new Date(f.accessed_at).toISOString() }, { onSuccess: () => setF(blank) })
  }
  return (
    <form onSubmit={submit} aria-label="Record licence evidence" className="grid gap-3 rounded-lg border border-line bg-surface p-3 sm:grid-cols-2">
      <p className="text-xs text-ink-2 sm:col-span-2">Record what you read at the source. The application does not fetch this address; quote the licence statement exactly as it appears.</p>
      <Field id="ev-url" label="Source address (https)"><input id="ev-url" className={input} value={f.url} onChange={(e) => set('url', e.target.value)} required /></Field>
      <Field id="ev-licence" label="Licence this source states (SPDX)"><input id="ev-licence" className={input} value={f.licence_spdx} onChange={(e) => set('licence_spdx', e.target.value)} placeholder="CC-BY-4.0" required /></Field>
      <Field id="ev-kind" label="Kind"><select id="ev-kind" className={input} value={f.kind} onChange={(e) => set('kind', e.target.value)}>{EVIDENCE_KINDS.map((k) => <option key={k} value={k}>{label(k)}</option>)}</select></Field>
      <Field id="ev-scope" label="Covers">
        <select id="ev-scope" className={input} value={f.scope} onChange={(e) => set('scope', e.target.value)}>
          <option value="images">Images</option><option value="annotations">Annotations</option><option value="both">Images and annotations</option>
        </select>
      </Field>
      <Field id="ev-accessed" label="Date you read it"><input id="ev-accessed" type="date" className={input} value={f.accessed_at} onChange={(e) => set('accessed_at', e.target.value)} required /></Field>
      <label className="flex items-center gap-2 self-end text-sm"><input type="checkbox" checked={f.official} onChange={(e) => set('official', e.target.checked)} /> Official source (the publisher or host itself, not a mirror or article)</label>
      <div className="sm:col-span-2">
        <Field id="ev-excerpt" label="Quoted licence statement (10 to 600 characters)"><textarea id="ev-excerpt" className={input} rows={3} value={f.excerpt} onChange={(e) => set('excerpt', e.target.value)} minLength={10} maxLength={600} required /></Field>
      </div>
      <div className="sm:col-span-2">
        <button className={btnPrimary} disabled={add.isPending}>{add.isPending ? 'Saving…' : 'Record evidence'}</button>
        {add.error != null && <p role="alert" className="mt-2 text-sm text-critical">{errorMessage(add.error)}</p>}
      </div>
    </form>
  )
}

export function OverviewTab({ ws, d, role }: { ws: string; d: DatasetDetailRecord; role: Role }) {
  const editable = d.kind === 'real' && (d.status === 'proposed' || d.status === 'under_review')
  return (
    <div className="space-y-6">
      <section aria-labelledby="ov-status" className="space-y-2">
        <h2 id="ov-status" className="font-semibold">Status</h2>
        <div className="flex flex-wrap items-center gap-2">
          <DatasetStatusChip status={d.status} />
          <LicenceVerdictChip verdict={d.licence_verdict} />
          {d.kind === 'real' && <OriginChip origin={d.image_origin} />}
        </div>
        {d.kind === 'real' && !isApproved(d) && <p className="text-sm text-ink-2"><strong>Candidate, not approved.</strong> Do not download it. This application never downloads datasets.</p>}
        {d.kind === 'real' && isApproved(d) && <p className="text-sm text-ink-2">Approved by {short(d.approved_by)} on {fmtDateTime(d.approved_at)}. Approval is a licensing finding, not a statement that the data is good enough to train or evaluate a model.</p>}
        {d.kind === 'synthetic' && <p className="text-sm text-ink-2">Synthetic test fixture. It is not biological data and supports no claim about plants.</p>}
      </section>

      <section aria-labelledby="ov-blockers" className="space-y-2">
        <h2 id="ov-blockers" className="font-semibold">Approval blockers</h2>
        <Blockers d={d} />
        {d.kind === 'real' && <p className="text-sm text-ink-2"><strong>Image origin:</strong> {originExplanation(d.image_origin)}</p>}
      </section>

      <section aria-labelledby="ov-licence" className="space-y-2">
        <h2 id="ov-licence" className="font-semibold">Licence and rights</h2>
        <dl className="grid gap-3 sm:grid-cols-3">
          <Fact name="Dataset licence">{d.licence_spdx}</Fact>
          <Fact name="Images licence">{d.images_licence_spdx}</Fact>
          <Fact name="Annotations licence">{d.has_annotations ? d.annotations_licence_spdx ?? 'not recorded' : 'no separate annotations'}</Fact>
          <Fact name="Commercial use">{d.commercial_use}</Fact>
          <Fact name="Redistribution">{d.redistribution}</Fact>
          <Fact name="Attribution">{d.attribution_required === null ? 'not recorded' : d.attribution_required ? 'required' : 'not required'}</Fact>
        </dl>
        {d.attribution_text && <p className="text-sm text-ink-2">Attribution text: {d.attribution_text}</p>}
        <dl className="grid gap-3 sm:grid-cols-2">
          <Fact name="Source"><SafeUrl url={d.source_url} /></Fact>
          <Fact name="Source read on">{d.accessed_at ? fmtDate(d.accessed_at) : 'not recorded'}</Fact>
          <Fact name="Intended use">{d.intended_use || 'not recorded'}</Fact>
        </dl>
      </section>

      <section aria-labelledby="ov-evidence" className="space-y-2">
        <h2 id="ov-evidence" className="font-semibold">Licence evidence</h2>
        {d.evidence.length === 0 && <p className="text-sm text-ink-2">No evidence has been recorded. Nothing here is verified.</p>}
        <ul className="space-y-2">
          {d.evidence.map((e) => (
            <li key={e.id} className="rounded-lg border border-line bg-surface p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <StatusChip tone={e.official ? 'live' : 'at-risk'}>{e.official ? 'Official source' : 'Not an official source'}</StatusChip>
                <StatusChip tone="neutral">{label(e.kind)}</StatusChip>
                <StatusChip tone="neutral">Covers {e.scope}</StatusChip>
                <span>states <code>{e.licence_spdx}</code></span>
              </div>
              <p className="mt-1"><SafeUrl url={e.url} /> <span className="text-xs text-ink-3">read {fmtDate(e.accessed_at)}, recorded by {short(e.recorded_by)}</span></p>
              <blockquote className="mt-1 border-l-2 border-line pl-2 text-ink-2">{e.excerpt}</blockquote>
            </li>
          ))}
        </ul>
        {editable && atLeast(role, 'manager') && <EvidenceForm ws={ws} d={d} />}
      </section>

      <section aria-labelledby="ov-workflow" className="space-y-2">
        <h2 id="ov-workflow" className="font-semibold">Review and approval</h2>
        {d.kind === 'synthetic' ? <p className="text-sm text-ink-2">Synthetic fixtures need no approval.</p> : <Workflow ws={ws} d={d} role={role} />}
      </section>

      <section aria-labelledby="ov-history" className="space-y-2">
        <h2 id="ov-history" className="font-semibold">History</h2>
        <ol className="space-y-1 text-sm">
          {d.history.map((h, i) => (
            <li key={i} className="rounded border border-line bg-surface p-2">
              <span className="font-medium">{h.from_status ? `${label(h.from_status)} → ` : ''}{label(h.to_status)}</span>{' '}
              <span className="text-xs text-ink-3">{fmtDateTime(h.at)} by {short(h.actor_id)}</span>
              {h.note && <p className="text-ink-2">{h.note}</p>}
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
