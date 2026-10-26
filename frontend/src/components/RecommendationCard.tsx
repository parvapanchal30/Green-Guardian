import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Recommendation } from '../api/types'
import { useAcceptRecommendation, useDismissRecommendation } from '../lib/slice'
import { useI18n, type TKey } from '../i18n'
import { MethodBadge, SeverityChip, btn, btnPrimary, input } from './domain'
import { Icon } from './icons'
import type { IconName } from './icon-set'
import { errorMessage } from './states'
import { StatusChip } from './StatusChip'

const ACCEPT_KINDS = new Set(['task', 'defer_task', 'issue'])

/** One icon per kind of rule, so suggestions can be told apart at a glance (ADR-069, idea 2). */
const RULE_ICON: Record<string, IconName> = { critical_health: 'pulse', health_decline: 'health', inspection_gap: 'look', irrigation_defer: 'rain' }
const SEVERITY_DISC: Record<string, string> = {
  critical: 'bg-critical-soft text-critical',
  high: 'bg-critical-soft text-critical',
  medium: 'bg-at-risk-soft text-at-risk',
  low: 'bg-info-soft text-info',
}

type Inputs = { kind?: string; not_known?: string[]; forecast?: { source?: string; as_of?: string; soil_moisture_note?: string } }
const inputsOf = (rec: Recommendation): Inputs => ((rec.evidence as { inputs?: Inputs }).inputs ?? {}) as Inputs
const stripStop = (s: string) => s.replace(/[.\s]+$/, '')

/** A rule-based suggestion with its reason. Only a manager can accept or dismiss; everyone can read why. */
export function RecommendationCard({ rec, ws, canDecide }: { rec: Recommendation; ws: string; canDecide: boolean }) {
  const { t, te, fmt } = useI18n()
  const accept = useAcceptRecommendation(ws)
  const dismiss = useDismissRecommendation(ws)
  const [why, setWhy] = useState(false)
  const [dismissing, setDismissing] = useState(false)
  const [reason, setReason] = useState('')
  const action = rec.proposed_action as { create?: string }
  const verb = t(`rec.accept.${ACCEPT_KINDS.has(action.create ?? '') ? action.create : 'issue'}` as TKey)
  const error = accept.error ?? dismiss.error
  const inputs = inputsOf(rec)
  const forecastBased = inputs.kind === 'advisory_forecast_based'
  const open = rec.status === 'open'
  const version = rec.rule_version != null ? t('rec.version', { n: rec.rule_version }) : ''

  return (
    <li className="flex gap-3 rounded-lg border border-line bg-surface p-3">
      <span aria-hidden="true" className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${SEVERITY_DISC[rec.severity] ?? SEVERITY_DISC.low}`}>
        <Icon name={RULE_ICON[rec.rule_key] ?? 'agent'} size={20} />
      </span>
      <div className="min-w-0 flex-1">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityChip severity={rec.severity} />
        <MethodBadge method={rec.method} />
        {forecastBased && <StatusChip tone="soon">{t('rec.advisory')}</StatusChip>}
        {!open && <StatusChip tone="neutral">{te('rec.status', rec.status)}</StatusChip>}
        {rec.outcome && <StatusChip tone="live">{te('rec.outcome', rec.outcome)}</StatusChip>}
        <Link to={`/w/${ws}/assets/${rec.asset_id}`} className="font-medium text-moss underline-offset-2 hover:underline">
          {rec.title}
        </Link>
        <span className="text-xs text-ink-3">{fmt.relative(rec.created_at)}</span>
      </div>
      {rec.outcome_detail && (
        <p className="mt-1 text-xs text-ink-2">
          {rec.outcome_detail}
          {rec.outcome_at ? ` · ${fmt.dateTime(rec.outcome_at)}` : ''}
        </p>
      )}
      {rec.dismissed_reason && <p className="mt-1 text-xs text-ink-2">{t('rec.dismissedReason', { reason: rec.dismissed_reason })}</p>}
      <button type="button" className="mt-1 text-xs text-ink-2 underline" aria-expanded={why} onClick={() => setWhy((v) => !v)}>
        {t('rec.why')}
      </button>
      {why && (
        <div className="mt-1 space-y-1 rounded bg-surface-2 p-2 text-sm text-ink-2">
          <p>
            {stripStop(rec.explanation)}.{' '}
            {t(forecastBased ? 'rec.producedForecast' : 'rec.producedRecorded', { rule: rec.rule_key, version })}
          </p>
          {inputs.forecast?.source && (
            <p className="text-xs">
              {t('rec.forecastSource', { source: inputs.forecast.source })}
              {inputs.forecast.as_of ? t('rec.asOf', { when: fmt.dateTime(inputs.forecast.as_of) }) : ''}.
            </p>
          )}
          {inputs.not_known && inputs.not_known.length > 0 && (
            <div className="text-xs">
              <p className="font-medium">{t('rec.notKnown')}</p>
              <ul className="list-disc pl-5">
                {inputs.not_known.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {open && canDecide && !dismissing && (
        <div className="mt-2 flex gap-2">
          <button type="button" className={btnPrimary} disabled={accept.isPending} onClick={() => accept.mutate({ id: rec.id, body: {} })}>
            {accept.isPending ? t('rec.working') : verb}
          </button>
          <button type="button" className={btn} onClick={() => setDismissing(true)}>
            {t('rec.dismiss')}
          </button>
        </div>
      )}
      {open && canDecide && dismissing && (
        <form
          className="mt-2 flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            dismiss.mutate({ id: rec.id, reason: reason.trim() })
          }}
        >
          <label className="sr-only" htmlFor={`why-${rec.id}`}>
            {t('rec.dismissReason')}
          </label>
          <input id={`why-${rec.id}`} className={`${input} max-w-sm`} value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t('rec.dismissPlaceholder')} minLength={3} required />
          <button className={btn} disabled={dismiss.isPending || reason.trim().length < 3}>
            {t('rec.confirmDismiss')}
          </button>
          <button type="button" className={btn} onClick={() => setDismissing(false)}>
            {t('rec.cancel')}
          </button>
        </form>
      )}
      {open && !canDecide && <p className="mt-2 text-xs text-ink-3">{t('rec.managerDecides')}</p>}
      {error != null && (
        <p role="alert" className="mt-2 text-sm text-critical">
          {errorMessage(error)}
        </p>
      )}
      </div>
    </li>
  )
}
