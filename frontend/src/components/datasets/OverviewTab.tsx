import { useState, type FormEvent } from 'react'
import { ProblemError } from '../../api/client'
import type { DatasetDetailRecord } from '../../api/types'
import { useI18n } from '../../i18n'
import { atLeast } from '../../lib/format'
import { useAddEvidence, useTransitionDataset } from '../../lib/datasets'
import type { Role } from '../../api/types'
import { Field, btn, btnPrimary, input } from '../domain'
import { errorMessage } from '../states'
import { StatusChip } from '../StatusChip'
import { DatasetStatusChip, Fact, LicenceVerdictChip, OriginChip, SafeUrl, isApproved, short } from './shared'

const EVIDENCE_KINDS = ['licence_page', 'readme', 'paper', 'repository', 'archive_record', 'data_card', 'other']

/** Blockers the server reported in a refused request (422 dataset_not_approvable), if any. */
export function blockersFrom(error: unknown): string[] {
  if (error instanceof ProblemError && Array.isArray(error.body.blockers)) return error.body.blockers.map(String)
  return []
}

function Blockers({ d }: { d: DatasetDetailRecord }) {
  const { t } = useI18n()
  if (d.kind === 'synthetic') return <p className="text-sm text-ink-2">{t('ds.ov.syntheticNoLicence')}</p>
  if (isApproved(d)) return <p className="text-sm text-ink-2">{t('ds.ov.noBlockersApproved')}</p>
  if (d.blockers.length === 0) return <p className="text-sm text-ink-2">{t('ds.ov.noBlockersReported')}</p>
  return (
    <div role="group" aria-label={t('ds.ov.blockersGroup')} className="rounded border border-at-risk p-3">
      <p className="text-sm font-medium">{t('ds.ov.blockersIntro', { count: d.blockers.length })}</p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-2">{d.blockers.map((b) => <li key={b}>{b}</li>)}</ul>
    </div>
  )
}

function Workflow({ ws, d, role }: { ws: string; d: DatasetDetailRecord; role: Role }) {
  const { t } = useI18n()
  const move = useTransitionDataset(ws, d.id)
  const [note, setNote] = useState('')
  const canReview = atLeast(role, 'manager')
  const canDecide = atLeast(role, 'admin')
  if (!canReview) return <p className="text-sm text-ink-3">{t('ds.ov.onlyManagers')}</p>
  if (d.status === 'rejected') return <p className="text-sm text-ink-2">{t('ds.ov.rejectedFinal')}</p>
  const refused = blockersFrom(move.error)
  const go = (to: string) => move.mutate({ to_status: to, note: note.trim() || undefined })
  return (
    <div className="space-y-2">
      <Field id="dataset-note" label={t('ds.ov.noteOptional')}><input id="dataset-note" className={input} value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} /></Field>
      <div className="flex flex-wrap gap-2">
        {(d.status === 'proposed' || d.status === 'approved') && (
          <button type="button" className={btn} disabled={move.isPending} onClick={() => go('under_review')}>
            {d.status === 'approved' ? t('ds.ov.reopen') : t('ds.ov.startReview')}
          </button>
        )}
        {d.status === 'under_review' && canDecide && (
          <button type="button" className={btnPrimary} disabled={move.isPending} onClick={() => go('approved')}>{t('ds.ov.approve')}</button>
        )}
        {canDecide && <button type="button" className={btn} disabled={move.isPending} onClick={() => go('rejected')}>{t('ds.ov.reject')}</button>}
      </div>
      {d.status === 'under_review' && !canDecide && <p className="text-xs text-ink-3">{t('ds.ov.ownerDecides')}</p>}
      {d.status === 'under_review' && canDecide && d.blockers.length > 0 && (
        <p className="text-xs text-ink-3">{t('ds.ov.serverRefuses')}</p>
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
  const { t, te } = useI18n()
  const add = useAddEvidence(ws, d.id)
  const blank = { url: '', kind: 'licence_page', scope: 'images', licence_spdx: '', excerpt: '', official: false, accessed_at: '' }
  const [f, setF] = useState(blank)
  const set = (k: keyof typeof blank, v: string | boolean) => setF((s) => ({ ...s, [k]: v }))
  const submit = (e: FormEvent) => {
    e.preventDefault()
    add.mutate({ ...f, licence_spdx: f.licence_spdx.trim(), accessed_at: new Date(f.accessed_at).toISOString() }, { onSuccess: () => setF(blank) })
  }
  return (
    <form onSubmit={submit} aria-label={t('ds.ev.form')} className="grid gap-3 rounded-lg border border-line bg-surface p-3 sm:grid-cols-2">
      <p className="text-xs text-ink-2 sm:col-span-2">{t('ds.ev.intro')}</p>
      <Field id="ev-url" label={t('ds.ev.url')}><input id="ev-url" className={input} value={f.url} onChange={(e) => set('url', e.target.value)} required /></Field>
      <Field id="ev-licence" label={t('ds.ev.licence')}><input id="ev-licence" className={input} value={f.licence_spdx} onChange={(e) => set('licence_spdx', e.target.value)} placeholder="CC-BY-4.0" required /></Field>
      <Field id="ev-kind" label={t('ds.ev.kind')}><select id="ev-kind" className={input} value={f.kind} onChange={(e) => set('kind', e.target.value)}>{EVIDENCE_KINDS.map((k) => <option key={k} value={k}>{te('evidenceKind', k)}</option>)}</select></Field>
      <Field id="ev-scope" label={t('ds.ev.covers')}>
        <select id="ev-scope" className={input} value={f.scope} onChange={(e) => set('scope', e.target.value)}>
          <option value="images">{t('ds.ev.scope.images')}</option><option value="annotations">{t('ds.ev.scope.annotations')}</option><option value="both">{t('ds.ev.scope.both')}</option>
        </select>
      </Field>
      <Field id="ev-accessed" label={t('ds.ev.accessed')}><input id="ev-accessed" type="date" className={input} value={f.accessed_at} onChange={(e) => set('accessed_at', e.target.value)} required /></Field>
      <label className="flex items-center gap-2 self-end text-sm"><input type="checkbox" checked={f.official} onChange={(e) => set('official', e.target.checked)} /> {t('ds.ev.official')}</label>
      <div className="sm:col-span-2">
        <Field id="ev-excerpt" label={t('ds.ev.excerpt')}><textarea id="ev-excerpt" className={input} rows={3} value={f.excerpt} onChange={(e) => set('excerpt', e.target.value)} minLength={10} maxLength={600} required /></Field>
      </div>
      <div className="sm:col-span-2">
        <button className={btnPrimary} disabled={add.isPending}>{add.isPending ? t('ds.saving') : t('ds.ev.submit')}</button>
        {add.error != null && <p role="alert" className="mt-2 text-sm text-critical">{errorMessage(add.error)}</p>}
      </div>
    </form>
  )
}

export function OverviewTab({ ws, d, role }: { ws: string; d: DatasetDetailRecord; role: Role }) {
  const { t, te, fmt } = useI18n()
  const editable = d.kind === 'real' && (d.status === 'proposed' || d.status === 'under_review')
  const notRecorded = t('ds.ov.notRecorded')
  return (
    <div className="space-y-6">
      <section aria-labelledby="ov-status" className="space-y-2">
        <h2 id="ov-status" className="font-semibold">{t('ds.ov.status')}</h2>
        <div className="flex flex-wrap items-center gap-2">
          <DatasetStatusChip status={d.status} />
          <LicenceVerdictChip verdict={d.licence_verdict} />
          {d.kind === 'real' && <OriginChip origin={d.image_origin} />}
        </div>
        {d.kind === 'real' && !isApproved(d) && <p className="text-sm text-ink-2"><strong>{t('ds.ov.candidate')}</strong> {t('ds.ov.doNotDownload')}</p>}
        {d.kind === 'real' && isApproved(d) && <p className="text-sm text-ink-2">{t('ds.ov.approvedBy', { who: short(d.approved_by), when: fmt.dateTime(d.approved_at) })}</p>}
        {d.kind === 'synthetic' && <p className="text-sm text-ink-2">{t('ds.ov.syntheticFixture')}</p>}
      </section>

      <section aria-labelledby="ov-blockers" className="space-y-2">
        <h2 id="ov-blockers" className="font-semibold">{t('ds.ov.blockers')}</h2>
        <Blockers d={d} />
        {d.kind === 'real' && <p className="text-sm text-ink-2"><strong>{t('ds.ov.imageOrigin')}</strong> {te('imageOriginExplain', d.image_origin)}</p>}
      </section>

      <section aria-labelledby="ov-licence" className="space-y-2">
        <h2 id="ov-licence" className="font-semibold">{t('ds.ov.licenceRights')}</h2>
        <dl className="grid gap-3 sm:grid-cols-3">
          <Fact name={t('ds.ov.datasetLicence')}>{d.licence_spdx}</Fact>
          <Fact name={t('ds.ov.imagesLicence')}>{d.images_licence_spdx}</Fact>
          <Fact name={t('ds.ov.annotationsLicence')}>{d.has_annotations ? d.annotations_licence_spdx ?? notRecorded : t('ds.ov.noAnnotations')}</Fact>
          <Fact name={t('ds.ov.commercial')}>{te('ds.tri', d.commercial_use)}</Fact>
          <Fact name={t('ds.ov.redistribution')}>{te('ds.tri', d.redistribution)}</Fact>
          <Fact name={t('ds.ov.attribution')}>{d.attribution_required === null ? notRecorded : d.attribution_required ? t('ds.ov.required') : t('ds.ov.notRequired')}</Fact>
        </dl>
        {d.attribution_text && <p className="text-sm text-ink-2">{t('ds.ov.attributionText', { text: d.attribution_text })}</p>}
        <dl className="grid gap-3 sm:grid-cols-2">
          <Fact name={t('ds.ov.source')}><SafeUrl url={d.source_url} /></Fact>
          <Fact name={t('ds.ov.sourceReadOn')}>{d.accessed_at ? fmt.date(d.accessed_at) : notRecorded}</Fact>
          <Fact name={t('ds.form.intendedUse')}>{d.intended_use || notRecorded}</Fact>
        </dl>
      </section>

      <section aria-labelledby="ov-evidence" className="space-y-2">
        <h2 id="ov-evidence" className="font-semibold">{t('ds.ov.evidence')}</h2>
        {d.evidence.length === 0 && <p className="text-sm text-ink-2">{t('ds.ov.noEvidence')}</p>}
        <ul className="space-y-2">
          {d.evidence.map((e) => (
            <li key={e.id} className="rounded-lg border border-line bg-surface p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <StatusChip tone={e.official ? 'live' : 'at-risk'}>{e.official ? t('ds.ov.official') : t('ds.ov.notOfficial')}</StatusChip>
                <StatusChip tone="neutral">{te('evidenceKind', e.kind)}</StatusChip>
                <StatusChip tone="neutral">{t('ds.ov.covers', { scope: te('ds.ev.scope', e.scope).toLowerCase() })}</StatusChip>
                <span>{t('ds.ov.states')} <code>{e.licence_spdx}</code></span>
              </div>
              <p className="mt-1"><SafeUrl url={e.url} /> <span className="text-xs text-ink-3">{t('ds.ov.readRecorded', { when: fmt.date(e.accessed_at), who: short(e.recorded_by) })}</span></p>
              <blockquote className="mt-1 border-l-2 border-line pl-2 text-ink-2">{e.excerpt}</blockquote>
            </li>
          ))}
        </ul>
        {editable && atLeast(role, 'manager') && <EvidenceForm ws={ws} d={d} />}
      </section>

      <section aria-labelledby="ov-workflow" className="space-y-2">
        <h2 id="ov-workflow" className="font-semibold">{t('ds.ov.workflow')}</h2>
        {d.kind === 'synthetic' ? <p className="text-sm text-ink-2">{t('ds.ov.syntheticNoApproval')}</p> : <Workflow ws={ws} d={d} role={role} />}
      </section>

      <section aria-labelledby="ov-history" className="space-y-2">
        <h2 id="ov-history" className="font-semibold">{t('ds.ov.history')}</h2>
        <ol className="space-y-1 text-sm">
          {d.history.map((h, i) => (
            <li key={i} className="rounded border border-line bg-surface p-2">
              <span className="font-medium">{h.from_status ? `${te('datasetState', h.from_status)} → ` : ''}{te('datasetState', h.to_status)}</span>{' '}
              <span className="text-xs text-ink-3">{t('ds.ov.whenBy', { when: fmt.dateTime(h.at), who: short(h.actor_id) })}</span>
              {h.note && <p className="text-ink-2">{h.note}</p>}
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
