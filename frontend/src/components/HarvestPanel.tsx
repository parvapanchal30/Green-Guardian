import { useState, type FormEvent } from 'react'
import type { Asset, HarvestRecord, HarvestUnit, Role } from '../api/types'
import { useI18n } from '../i18n'
import { useCorrectHarvest, useHarvests, useRecordHarvest } from '../lib/harvests'
import { enteredAt } from '../lib/lifecycle'
import { atLeast } from '../lib/format'
import { Field, btn, btnPrimary, input } from './domain'
import { ErrorState, LoadingBlock, errorMessage } from './states'
import { StatusChip } from './StatusChip'

const UNITS: HarvestUnit[] = ['kg', 't', 'count', 'l']
const MIN_REASON = 10

/**
 * What was harvested from this asset. Totals are per unit and only kg and t are ever added together (as weight). The history
 * is append-only: a manager replaces a mistaken record with a corrected one and a reason, the original stays visible.
 */
export function HarvestPanel({ ws, asset, role }: { ws: string; asset: Asset; role: Role }) {
  const { t, te, fmt } = useI18n()
  const harvests = useHarvests(ws, asset.id)
  const record = useRecordHarvest(ws, asset.id)
  const correct = useCorrectHarvest(ws, asset.id)
  const [problem, setProblem] = useState<string | null>(null)
  const [correcting, setCorrecting] = useState<HarvestRecord | null>(null)
  const canRecord = atLeast(role, 'worker') && asset.is_active
  const isManager = atLeast(role, 'manager')
  const qty = (q: number, unit: string) => `${fmt.number(q, { maximumFractionDigits: 3 })} ${te('unit', unit)}`

  if (harvests.isLoading) return <LoadingBlock label={t('harvest.loading')} />
  if (harvests.error || !harvests.data) return <ErrorState error={harvests.error ?? new Error(t('harvest.unavailable'))} onRetry={() => harvests.refetch()} />
  const { totals, history } = harvests.data

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    const f = new FormData(form)
    const text = (k: string) => String(f.get(k) ?? '').trim()
    const quantity = Number(text('quantity'))
    const reason = text('note')
    if (!Number.isFinite(quantity) || (!correcting && quantity <= 0) || (correcting && (text('quantity') === '' || quantity < 0))) {
      return setProblem(correcting ? t('harvest.errCorrectedQuantity') : t('harvest.errQuantity'))
    }
    if (correcting && reason.length < MIN_REASON) return setProblem(t('harvest.errReason', { min: MIN_REASON }))
    setProblem(null)
    const body = { quantity, unit: text('unit') as HarvestUnit, harvested_at: enteredAt(text('date')), grade: text('grade') || undefined, note: reason || undefined }
    const done = { onSuccess: () => { form.reset(); setCorrecting(null) } }
    if (correcting) correct.mutate({ ...body, id: correcting.id, note: reason }, done)
    else record.mutate(body, done)
  }

  const pending = record.isPending || correct.isPending
  const serverError = record.error ?? correct.error

  return (
    <section aria-labelledby="harvest">
      <h2 id="harvest" className="mb-2 flex flex-wrap items-center gap-2 font-semibold">
        {t('harvest.title')}
        {totals.records > 0 && (
          <span className="text-sm font-normal text-ink-2">
            {Object.entries(totals.by_unit).map(([u, q]) => qty(q, u)).join(' · ')}
            {totals.mass_tonnes > 0 && Object.keys(totals.by_unit).filter((u) => u === 'kg' || u === 't').length > 1 ? t('harvest.weight', { tonnes: totals.mass_tonnes }) : ''}
          </span>
        )}
      </h2>

      {history.length === 0 && <p className="mb-3 text-sm text-ink-3">{t('harvest.none')}</p>}
      <ol aria-label={t('harvest.history')} className="mb-3 space-y-1 text-sm">
        {history.map((h) => (
          <li key={h.id} className={`flex flex-wrap items-baseline gap-x-2 ${h.effective ? '' : 'text-ink-3 line-through decoration-1'}`}>
            <span className="text-xs text-ink-3 no-underline">{fmt.dateTime(h.harvested_at)}</span>
            <span className="font-medium">{qty(h.quantity, h.unit)}</span>
            {h.grade && <span>{t('harvest.grade', { grade: h.grade })}</span>}
            {h.supersedes_id && <StatusChip tone="at-risk">{h.withdrawn ? t('harvest.withdrawn') : t('harvest.correctionChip')}</StatusChip>}
            {!h.effective && <StatusChip tone="neutral">{t('harvest.replaced')}</StatusChip>}
            {h.note && <span className="text-ink-2">{h.note}</span>}
            {isManager && h.effective && !h.withdrawn && (
              <button type="button" className={`${btn} px-2 py-0.5 text-xs`} onClick={() => { setCorrecting(h); setProblem(null) }}>{t('harvest.correct')}</button>
            )}
          </li>
        ))}
      </ol>

      {!canRecord && !asset.is_active && <p className="text-sm text-ink-3">{t('harvest.exited')}</p>}
      {canRecord && (
        <form onSubmit={submit} className="space-y-3 rounded-lg border border-line bg-surface p-3" aria-label={correcting ? t('harvest.formCorrect') : t('harvest.formRecord')}>
          {correcting && (
            <p className="text-sm text-ink-2">
              {t('harvest.correcting', { what: qty(correcting.quantity, correcting.unit) })}{' '}
              <button type="button" className="text-moss underline" onClick={() => setCorrecting(null)}>{t('harvest.cancelCorrection')}</button>
            </p>
          )}
          <div className="grid gap-3 sm:grid-cols-4">
            <Field id="h-qty" label={t('harvest.quantity')}>
              <input id="h-qty" name="quantity" type="number" step="any" min={0} className={input} defaultValue={correcting?.quantity} key={correcting?.id ?? 'new'} />
            </Field>
            <Field id="h-unit" label={t('harvest.unit')}>
              <select id="h-unit" name="unit" className={input} defaultValue={correcting?.unit ?? 'kg'} key={`u-${correcting?.id ?? 'new'}`}>
                {UNITS.map((u) => <option key={u} value={u}>{te('unit', u)}</option>)}
              </select>
            </Field>
            <Field id="h-date" label={t('harvest.date')} hint={t('harvest.dateHint')}>
              <input id="h-date" name="date" type="date" className={input} />
            </Field>
            <Field id="h-grade" label={t('harvest.gradeOptional')}>
              <input id="h-grade" name="grade" className={input} maxLength={40} defaultValue={correcting?.grade ?? ''} key={`g-${correcting?.id ?? 'new'}`} />
            </Field>
          </div>
          <Field id="h-note" label={correcting ? t('harvest.reasonRequired') : t('harvest.noteOptional')}>
            <input id="h-note" name="note" className={input} maxLength={1000} />
          </Field>
          {(problem || serverError) && <p role="alert" className="text-sm text-critical">{problem ?? errorMessage(serverError)}</p>}
          <button type="submit" className={btnPrimary} disabled={pending}>{pending ? t('harvest.saving') : correcting ? t('harvest.saveCorrection') : t('harvest.saveRecord')}</button>
          <p className="text-xs text-ink-3">{t('harvest.appendOnly')}</p>
        </form>
      )}
    </section>
  )
}
