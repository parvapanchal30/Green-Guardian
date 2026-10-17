import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Recommendation } from '../api/types'
import { useAcceptRecommendation, useDismissRecommendation } from '../lib/slice'
import { fmtDateTime, label, relative } from '../lib/format'
import { MethodBadge, SeverityChip, btn, btnPrimary, input } from './domain'
import { errorMessage } from './states'
import { StatusChip } from './StatusChip'

const ACCEPT_VERB: Record<string, string> = {
  task: 'Accept: create inspection task',
  defer_task: 'Accept: postpone the watering task',
  issue: 'Accept: open issue',
}

const OUTCOME_TEXT: Record<NonNullable<Recommendation['outcome']>, string> = {
  task_completed: 'Task completed',
  task_cancelled: 'Task cancelled',
  issue_resolved: 'Issue resolved',
  issue_closed: 'Issue closed without a fix',
  deferral_applied: 'Task postponed',
}

type Inputs = { kind?: string; not_known?: string[]; forecast?: { source?: string; as_of?: string; soil_moisture_note?: string } }
const inputsOf = (rec: Recommendation): Inputs => ((rec.evidence as { inputs?: Inputs }).inputs ?? {}) as Inputs
const stripStop = (s: string) => s.replace(/[.\s]+$/, '')

/** A rule-based suggestion with its reason. Only a manager can accept or dismiss; everyone can read why. */
export function RecommendationCard({ rec, ws, canDecide }: { rec: Recommendation; ws: string; canDecide: boolean }) {
  const accept = useAcceptRecommendation(ws)
  const dismiss = useDismissRecommendation(ws)
  const [why, setWhy] = useState(false)
  const [dismissing, setDismissing] = useState(false)
  const [reason, setReason] = useState('')
  const action = rec.proposed_action as { create?: string }
  const verb = ACCEPT_VERB[action.create ?? 'issue'] ?? ACCEPT_VERB.issue
  const error = accept.error ?? dismiss.error
  const inputs = inputsOf(rec)
  const forecastBased = inputs.kind === 'advisory_forecast_based'
  const open = rec.status === 'open'
  const version = rec.rule_version != null ? ` (version ${rec.rule_version})` : ''

  return (
    <li className="rounded-lg border border-line bg-surface p-3">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityChip severity={rec.severity} />
        <MethodBadge method={rec.method} />
        {forecastBased && <StatusChip tone="soon">Advisory · forecast-based</StatusChip>}
        {!open && <StatusChip tone="neutral">{label(rec.status)}</StatusChip>}
        {rec.outcome && <StatusChip tone="live">{OUTCOME_TEXT[rec.outcome]}</StatusChip>}
        <Link to={`/w/${ws}/assets/${rec.asset_id}`} className="font-medium text-moss underline-offset-2 hover:underline">
          {rec.title}
        </Link>
        <span className="text-xs text-ink-3">{relative(rec.created_at)}</span>
      </div>
      {rec.outcome_detail && (
        <p className="mt-1 text-xs text-ink-2">
          {rec.outcome_detail}
          {rec.outcome_at ? ` · ${fmtDateTime(rec.outcome_at)}` : ''}
        </p>
      )}
      {rec.dismissed_reason && <p className="mt-1 text-xs text-ink-2">Dismissed: {rec.dismissed_reason}</p>}
      <button type="button" className="mt-1 text-xs text-ink-2 underline" aria-expanded={why} onClick={() => setWhy((v) => !v)}>
        Why?
      </button>
      {why && (
        <div className="mt-1 space-y-1 rounded bg-surface-2 p-2 text-sm text-ink-2">
          <p>
            {stripStop(rec.explanation)}.{' '}
            {forecastBased ? (
              <>
                Produced by rule <code>{rec.rule_key}</code>
                {version} from a weather forecast. It is advisory: a forecast is not a measurement of soil moisture.
              </>
            ) : (
              <>
                Produced by rule <code>{rec.rule_key}</code>
                {version} on recorded data; this is not a prediction.
              </>
            )}
          </p>
          {inputs.forecast?.source && (
            <p className="text-xs">
              Forecast source: {inputs.forecast.source}
              {inputs.forecast.as_of ? `, as of ${fmtDateTime(inputs.forecast.as_of)}` : ''}.
            </p>
          )}
          {inputs.not_known && inputs.not_known.length > 0 && (
            <div className="text-xs">
              <p className="font-medium">Not known to this rule:</p>
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
            {accept.isPending ? 'Working…' : verb}
          </button>
          <button type="button" className={btn} onClick={() => setDismissing(true)}>
            Dismiss
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
            Reason for dismissing
          </label>
          <input id={`why-${rec.id}`} className={`${input} max-w-sm`} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (min 3 characters)" minLength={3} required />
          <button className={btn} disabled={dismiss.isPending || reason.trim().length < 3}>
            Confirm dismiss
          </button>
          <button type="button" className={btn} onClick={() => setDismissing(false)}>
            Cancel
          </button>
        </form>
      )}
      {open && !canDecide && <p className="mt-2 text-xs text-ink-3">A manager decides whether to act on this.</p>}
      {error != null && (
        <p role="alert" className="mt-2 text-sm text-critical">
          {errorMessage(error)}
        </p>
      )}
    </li>
  )
}
