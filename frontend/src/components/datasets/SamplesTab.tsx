import { useState } from 'react'
import type { DatasetDetailRecord, DatasetSampleRecord, Role } from '../../api/types'
import { useI18n } from '../../i18n'
import { atLeast } from '../../lib/format'
import { useDatasetSamples, useReviewSample, useReviewSummary, useSampleReviews } from '../../lib/datasets'
import { Field, Pagination, btn, btnPrimary, input } from '../domain'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../states'
import { StatusChip } from '../StatusChip'
import { ImportPanel } from './ImportPanel'
import { LabelStatusChip, short } from './shared'

const PAGE = 25
const STATUSES = ['', 'unreviewed', 'under_review', 'accepted', 'rejected', 'corrected'] as const
const MIN_EVIDENCE = 10

function History({ ws, datasetId, sampleId }: { ws: string; datasetId: string; sampleId: string }) {
  const { t, te, fmt } = useI18n()
  const q = useSampleReviews(ws, datasetId, sampleId)
  if (q.isLoading) return <LoadingBlock label={t('ds.s.loadingHistory')} />
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  if (!q.data || q.data.length === 0) return <p className="text-sm text-ink-2">{t('ds.s.noReview')}</p>
  return (
    <ol aria-label={t('ds.s.history')} className="space-y-1 text-sm">
      {q.data.map((r) => (
        <li key={r.id} className="rounded border border-line bg-surface p-2">
          <span className="font-medium">{te('labelStatus', r.from_status)} → {te('labelStatus', r.to_status)}</span>
          {r.from_label !== r.to_label && <span> · {t('ds.s.labelChange', { from: r.from_label ?? '—', to: r.to_label ?? '—' })}</span>}
          <span className="text-xs text-ink-3"> · {fmt.dateTime(r.at)} · {t('ds.s.reviewer', { who: short(r.reviewer_id) })}</span>
          <p className="text-xs text-ink-3">
            {r.reviewer_qualification ? t('protocol.declared', { q: r.reviewer_qualification }) : t('protocol.noDeclared')}
            {' — '}{r.qualification_verified ? t('protocol.verified') : t('protocol.unverified')}
          </p>
          {r.evidence && <p className="text-ink-2">{t('ds.s.evidence', { text: r.evidence })}</p>}
        </li>
      ))}
    </ol>
  )
}

function ReviewForm({ ws, datasetId, s }: { ws: string; datasetId: string; s: DatasetSampleRecord }) {
  const { t } = useI18n()
  const review = useReviewSample(ws, datasetId)
  const [evidence, setEvidence] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [qual, setQual] = useState('')
  const send = (to: string, extra: Record<string, unknown> = {}) =>
    review.mutate(
      { sampleId: s.id, body: { to_status: to, evidence: evidence.trim() || undefined, reviewer_qualification: qual.trim() || undefined, ...extra } },
      { onSuccess: () => { setEvidence(''); setNewLabel('') } },
    )
  const hasEvidence = evidence.trim().length >= MIN_EVIDENCE
  const decided = s.label_status === 'accepted' || s.label_status === 'rejected' || s.label_status === 'corrected'
  return (
    <div className="space-y-2 rounded border border-line p-3">
      {s.label_status === 'under_review' && (
        <>
          <Field id={`ev-${s.id}`} label={t('ds.s.evidenceLabel', { n: MIN_EVIDENCE })}>
            <textarea id={`ev-${s.id}`} className={input} rows={2} value={evidence} onChange={(e) => setEvidence(e.target.value)} />
          </Field>
          <Field id={`lab-${s.id}`} label={t('ds.s.newLabel')}>
            <input id={`lab-${s.id}`} className={input} value={newLabel} onChange={(e) => setNewLabel(e.target.value)} maxLength={120} />
          </Field>
        </>
      )}
      <Field id={`q-${s.id}`} label={t('protocol.qualification')}>
        <input id={`q-${s.id}`} className={input} value={qual} onChange={(e) => setQual(e.target.value)} maxLength={300} />
      </Field>
      <div className="flex flex-wrap gap-2">
        {s.label_status === 'unreviewed' && <button type="button" className={btn} disabled={review.isPending} onClick={() => send('under_review')}>{t('ds.ov.startReview')}</button>}
        {s.label_status === 'under_review' && (
          <>
            <button type="button" className={btnPrimary} disabled={review.isPending || !hasEvidence || !s.label} onClick={() => send('accepted')}>{t('ds.s.accept')}</button>
            <button type="button" className={btn} disabled={review.isPending || !hasEvidence} onClick={() => send('rejected')}>{t('ds.s.reject')}</button>
            <button type="button" className={btn} disabled={review.isPending || !hasEvidence || !newLabel.trim() || newLabel.trim() === s.label} onClick={() => send('corrected', { to_label: newLabel.trim() })}>{t('ds.s.correct')}</button>
            <button type="button" className={btn} disabled={review.isPending} onClick={() => send('unreviewed')}>{t('ds.s.release')}</button>
          </>
        )}
        {decided && <button type="button" className={btn} disabled={review.isPending} onClick={() => send('under_review')}>{t('ds.s.reopen')}</button>}
      </div>
      {review.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(review.error)}</p>}
    </div>
  )
}

function Row({ ws, d, s, role }: { ws: string; d: DatasetDetailRecord; s: DatasetSampleRecord; role: Role }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  return (
    <li className="rounded-lg border border-line bg-surface p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <code>{s.external_id}</code>
        <LabelStatusChip status={s.label_status} />
        <span>{t('ds.s.label')} {s.label ? <strong>{s.label}</strong> : <em className="text-ink-3">{t('ds.s.none')}</em>}</span>
        <span className="text-xs text-ink-3">{t('ds.s.group', { group: s.group_key ?? t('ds.s.none') })}</span>
        {s.file_status === 'invalid' && <StatusChip tone="critical">{t('ds.s.invalidFile')}</StatusChip>}
        {s.is_synthetic && <StatusChip tone="neutral">{t('ds.synthetic')}</StatusChip>}
        <button type="button" className="ml-auto text-xs underline" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {open ? t('ds.s.hide') : t('ds.s.show')}
        </button>
      </div>
      {open && (
        <div className="mt-2 space-y-2">
          <History ws={ws} datasetId={d.id} sampleId={s.id} />
          {atLeast(role, 'manager') ? <ReviewForm ws={ws} datasetId={d.id} s={s} /> : <p className="text-xs text-ink-3">{t('ds.s.onlyManagersReview')}</p>}
        </div>
      )}
    </li>
  )
}

export function SamplesTab({ ws, d, role }: { ws: string; d: DatasetDetailRecord; role: Role }) {
  const { t, te } = useI18n()
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)
  const summary = useReviewSummary(ws, d.id)
  const list = useDatasetSamples(ws, d.id, { label_status: status || undefined, limit: PAGE, offset })
  return (
    <div className="space-y-4">
      <p className="rounded-lg border border-line bg-surface p-3 text-sm text-ink-2">{t('ds.unverifiedNote')}</p>
      {atLeast(role, 'manager') ? <ImportPanel ws={ws} d={d} /> : <p className="text-xs text-ink-3">{t('ds.s.onlyManagersAdd')}</p>}
      {summary.error ? <ErrorState error={summary.error} /> : summary.data && (
        <div aria-label={t('ds.s.summary')} className="flex flex-wrap items-center gap-2 text-sm">
          {Object.entries(summary.data.by_status).map(([k, v]) => <StatusChip key={k} tone="neutral">{te('labelStatus', k)}: {v}</StatusChip>)}
          <span>{t('ds.s.reviewedPct', { pct: Math.round(summary.data.reviewed_fraction * 100) })}</span>
          <StatusChip tone="at-risk">{t('ds.s.verifiedReviewers', { n: summary.data.qualified_reviewers_verified })}</StatusChip>
        </div>
      )}
      <div className="max-w-xs">
        <Field id="sample-status" label={t('ds.s.filter')}>
          <select id="sample-status" className={input} value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0) }}>
            {STATUSES.map((s) => <option key={s} value={s}>{s ? te('labelStatus', s) : t('ds.s.anyStatus')}</option>)}
          </select>
        </Field>
      </div>
      {list.isLoading && <LoadingBlock label={t('ds.s.loading')} />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data && list.data.total === 0 && (
        <EmptyState title={status ? t('ds.s.noneWithStatus') : t('ds.s.noneRegistered')}>
          {d.kind === 'real' && d.status !== 'approved' ? t('ds.s.onlyAfterApproval') : t('ds.s.addHint')}
        </EmptyState>
      )}
      <ul className="space-y-2">{list.data?.items.map((s) => <Row key={s.id} ws={ws} d={d} s={s} role={role} />)}</ul>
      {list.data && list.data.total > PAGE && <Pagination total={list.data.total} limit={PAGE} offset={offset} onChange={setOffset} />}
    </div>
  )
}
