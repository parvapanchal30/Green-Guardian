import { useState, type FormEvent } from 'react'
import type { Asset, Role, StageChoice } from '../api/types'
import { useI18n } from '../i18n'
import { enteredAt, useLifecycle, useLifecycleTemplate, useRecordStage } from '../lib/lifecycle'
import { atLeast } from '../lib/format'
import { Field, btnPrimary, input } from './domain'
import { ErrorState, LoadingBlock, errorMessage } from './states'
import { StatusChip } from './StatusChip'

const MIN_REASON = 10

/**
 * Where the asset is in its lifecycle, what happened before, and (for people allowed to) a form to record a change.
 * The server is the authority: it lists the stages that can be recorded now, enforces roles and the correction rule,
 * and the list of exits depends on whether the asset is an individual or a population.
 */
export function LifecyclePanel({ ws, asset, role }: { ws: string; asset: Asset; role: Role }) {
  const { t, te, fmt } = useI18n()
  const lifecycle = useLifecycle(ws, asset.id)
  const isManager = atLeast(role, 'manager')
  const canRecord = atLeast(role, 'worker')
  const [correction, setCorrection] = useState(false)
  const template = useLifecycleTemplate(ws, correction)
  const record = useRecordStage(ws, asset.id)
  const [problem, setProblem] = useState<string | null>(null)

  if (lifecycle.isLoading) return <LoadingBlock label={t('lifecycle.loading')} />
  if (lifecycle.error || !lifecycle.data) return <ErrorState error={lifecycle.error ?? new Error(t('lifecycle.unavailable'))} onRetry={() => lifecycle.refetch()} />
  const lc = lifecycle.data

  // Normal changes: exactly what the server listed. Corrections (managers only): any other stage of the template.
  const exits = template.data ? (asset.tracking_mode === 'population' ? template.data.exits_population : template.data.exits_individual) : []
  const allStages: StageChoice[] = template.data ? [...template.data.stages, ...exits] : []
  const choices: StageChoice[] = correction ? allStages.filter((c) => c.key !== lc.current_stage) : lc.next_choices
  const formVisible = canRecord && (lc.is_active || isManager)
  const currentLabel = te('stage', lc.current_stage, lc.history.find((h) => h.stage === lc.current_stage)?.stage_label)

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    const f = new FormData(form)
    const text = (k: string) => String(f.get(k) ?? '').trim()
    const stage = text('stage')
    if (!stage) return setProblem(t('lifecycle.chooseStage'))
    if (correction && text('note').length < MIN_REASON) return setProblem(t('lifecycle.reasonShort', { min: MIN_REASON }))
    setProblem(null)
    record.mutate(
      { stage, correction, entered_at: enteredAt(text('entered')), note: text('note') || undefined },
      { onSuccess: () => { form.reset(); setCorrection(false) } },
    )
  }

  return (
    <section aria-labelledby="lifecycle">
      <h2 id="lifecycle" className="mb-2 flex flex-wrap items-center gap-2 font-semibold">
        {t('lifecycle.title')}
        <StatusChip tone={lc.is_active ? 'neutral' : 'critical'}>{currentLabel}</StatusChip>
        {!lc.is_active && <span className="text-sm font-normal text-ink-2">{t('lifecycle.exitedNote')}</span>}
      </h2>

      <ol aria-label={t('lifecycle.history')} className="mb-3 space-y-1 text-sm">
        {lc.history.map((h) => (
          <li key={h.id} className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-xs text-ink-3">{fmt.dateTime(h.entered_at)}</span>
            <span className="font-medium">{h.previous_stage ? `${te('stage', h.previous_stage)} → ` : ''}{te('stage', h.stage, h.stage_label)}</span>
            {h.correction && <StatusChip tone="at-risk">{t('lifecycle.correction')}</StatusChip>}
            {h.note && <span className="text-ink-2">{h.note}</span>}
          </li>
        ))}
      </ol>

      {!canRecord && <p className="text-sm text-ink-3">{t('lifecycle.onlyWorkers')}</p>}
      {canRecord && !lc.is_active && !isManager && (
        <p className="text-sm text-ink-2">{t('lifecycle.managerCanReinstate')}</p>
      )}
      {formVisible && (
        <form onSubmit={submit} className="space-y-3 rounded-lg border border-line bg-surface p-3" aria-label={t('lifecycle.formLabel')}>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field id="lc-stage" label={correction ? t('lifecycle.correctTo') : t('lifecycle.newStage')}>
              <select id="lc-stage" name="stage" className={input} defaultValue="" disabled={correction && template.isLoading}>
                <option value="">{t('lifecycle.choose')}</option>
                {choices.map((c) => {
                  const blocked = c.manager_only && !isManager
                  return (
                    <option key={c.key} value={c.key} disabled={blocked}>
                      {te('stage', c.key, c.label)}{c.kind === 'exit' ? t('lifecycle.endsLifecycle') : ''}{blocked ? t('lifecycle.managerOnly') : ''}
                    </option>
                  )
                })}
              </select>
            </Field>
            <Field id="lc-date" label={t('lifecycle.when')} hint={t('lifecycle.whenHint')}>
              <input id="lc-date" name="entered" type="date" className={input} />
            </Field>
            <Field id="lc-note" label={correction ? t('lifecycle.reasonRequired') : t('lifecycle.note')}>
              <input id="lc-note" name="note" className={input} maxLength={1000} />
            </Field>
          </div>
          {isManager && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={correction} onChange={(e) => setCorrection(e.target.checked)} />
              {t('lifecycle.isCorrection')}
            </label>
          )}
          {(problem || record.error) && <p role="alert" className="text-sm text-critical">{problem ?? errorMessage(record.error)}</p>}
          <button type="submit" className={btnPrimary} disabled={record.isPending}>{record.isPending ? t('lifecycle.saving') : t('lifecycle.record')}</button>
          <p className="text-xs text-ink-3">{t('lifecycle.appendOnly')}</p>
        </form>
      )}
    </section>
  )
}
