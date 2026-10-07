import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Recommendation } from '../api/types'
import { useAcceptRecommendation, useDismissRecommendation } from '../lib/slice'
import { relative } from '../lib/format'
import { MethodBadge, SeverityChip, btn, btnPrimary, input } from './domain'
import { errorMessage } from './states'

/** A rule-based suggestion with its reason. Only a manager can accept or dismiss; everyone can read why. */
export function RecommendationCard({ rec, ws, canDecide }: { rec: Recommendation; ws: string; canDecide: boolean }) {
  const accept = useAcceptRecommendation(ws)
  const dismiss = useDismissRecommendation(ws)
  const [why, setWhy] = useState(false)
  const [dismissing, setDismissing] = useState(false)
  const [reason, setReason] = useState('')
  const action = rec.proposed_action as { create?: string }
  const verb = action.create === 'task' ? 'Accept: create inspection task' : 'Accept: open issue'
  const error = accept.error ?? dismiss.error

  return (
    <li className="rounded-lg border border-line bg-surface p-3">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityChip severity={rec.severity} />
        <MethodBadge method={rec.method} />
        <Link to={`/w/${ws}/assets/${rec.asset_id}`} className="font-medium text-moss underline-offset-2 hover:underline">
          {rec.title}
        </Link>
        <span className="text-xs text-ink-3">{relative(rec.created_at)}</span>
      </div>
      <button type="button" className="mt-1 text-xs text-ink-2 underline" aria-expanded={why} onClick={() => setWhy((v) => !v)}>
        Why?
      </button>
      {why && (
        <p className="mt-1 rounded bg-surface-2 p-2 text-sm text-ink-2">
          {rec.explanation}. Produced by rule <code>{rec.rule_key}</code> on recorded data; this is not a prediction.
        </p>
      )}
      {canDecide && !dismissing && (
        <div className="mt-2 flex gap-2">
          <button type="button" className={btnPrimary} disabled={accept.isPending} onClick={() => accept.mutate({ id: rec.id, body: {} })}>
            {accept.isPending ? 'Working…' : verb}
          </button>
          <button type="button" className={btn} onClick={() => setDismissing(true)}>
            Dismiss
          </button>
        </div>
      )}
      {canDecide && dismissing && (
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
      {!canDecide && <p className="mt-2 text-xs text-ink-3">A manager decides whether to act on this.</p>}
      {error != null && (
        <p role="alert" className="mt-2 text-sm text-critical">
          {errorMessage(error)}
        </p>
      )}
    </li>
  )
}
