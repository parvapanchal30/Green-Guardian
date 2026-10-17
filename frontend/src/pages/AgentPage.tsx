import { useState } from 'react'
import type { AgentRunRecord } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { MethodBadge, PageHeader, btnPrimary } from '../components/domain'
import { RecommendationCard } from '../components/RecommendationCard'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { StatusChip } from '../components/StatusChip'
import { atLeast, fmtDateTime, label } from '../lib/format'
import { useAgentRules, useAgentRuns, useRecommendations, useRunAgent } from '../lib/slice'

const FILTERS = [
  { key: 'open', text: 'Open' },
  { key: 'accepted', text: 'Accepted' },
  { key: 'dismissed', text: 'Dismissed' },
  { key: 'expired', text: 'Expired' },
] as const
type Filter = (typeof FILTERS)[number]['key']

const STATUS_TONE = { succeeded: 'live', failed: 'critical', running: 'building' } as const

/** What a run could not do, in words, so an empty result is never mistaken for "all clear". */
function runNotes(run: AgentRunRecord): string[] {
  const notes: string[] = []
  const skipped = run.diagnostics.skipped ?? {}
  for (const [reason, n] of Object.entries(skipped)) notes.push(`${n} × ${label(reason).toLowerCase()}`)
  const w = run.diagnostics.weather
  if (w?.requested && (w.unavailable ?? 0) > 0) notes.push(`weather unavailable for ${w.unavailable} location(s)`)
  return notes
}

function RunRow({ run }: { run: AgentRunRecord }) {
  const notes = runNotes(run)
  return (
    <li className="rounded-lg border border-line bg-surface p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip tone={STATUS_TONE[run.status]}>{label(run.status)}</StatusChip>
        <StatusChip tone="neutral">{run.trigger === 'scheduled' ? 'Scheduled' : 'Manual'}</StatusChip>
        <span>{fmtDateTime(run.started_at)}</span>
        {run.duration_s != null && <span className="text-xs text-ink-3">{run.duration_s.toFixed(1)} s</span>}
      </div>
      {run.status === 'failed' ? (
        <p role="alert" className="mt-1 text-critical">{run.error ?? 'The run failed.'}</p>
      ) : (
        <p className="mt-1 text-ink-2">
          {run.evaluated_assets} asset(s) checked · {run.recommendations_created} new · {run.recommendations_expired} expired
        </p>
      )}
      {notes.length > 0 && <p className="mt-1 text-xs text-ink-3">Not evaluated or skipped: {notes.join(' · ')}</p>}
    </li>
  )
}

export function AgentPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const [filter, setFilter] = useState<Filter>('open')
  const rules = useAgentRules(ws)
  const recs = useRecommendations(ws, { status: filter, limit: 25 })
  const runs = useAgentRuns(ws, 10)
  const run = useRunAgent(ws)
  const canDecide = atLeast(workspace.role, 'manager')

  return (
    <div className="space-y-6">
      <PageHeader title="Botanical Operations Agent" subtitle="Deterministic rules over recorded data. It suggests; a person decides.">
        <StatusChip tone="live">Rules + statistics</StatusChip>
        {canDecide && <button type="button" className={btnPrimary} disabled={run.isPending} onClick={() => run.mutate(undefined as never)}>{run.isPending ? 'Checking…' : 'Run checks now'}</button>}
      </PageHeader>

      <p className="max-w-prose rounded-lg border border-line bg-surface p-3 text-sm text-ink-2">
        This agent applies thresholds to what has been recorded, on a schedule and whenever you run it. It does not use machine learning or a language model, and it never creates issues or tasks on its own.
        The irrigation advice is based on a weather <em>forecast</em>: it does not know how wet the soil is or what the plant needs, and it is withheld when a plant shows signs of water stress.
        Prediction, recommendation engines and optimisation are planned for later versions and are shown as “Coming soon” elsewhere.
      </p>

      {run.data && (
        <p role="status" className="text-sm text-ink-2">
          Checked {run.data.evaluated_assets} asset(s); {run.data.created.length} new and {run.data.expired} expired suggestion(s).
        </p>
      )}
      {run.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(run.error)}</p>}

      <section aria-labelledby="suggestions">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 id="suggestions" className="font-semibold">Suggestions</h2>
          <div role="group" aria-label="Suggestion status" className="flex gap-1">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                type="button"
                aria-pressed={filter === f.key}
                onClick={() => setFilter(f.key)}
                className={`rounded border px-2 py-1 text-xs ${filter === f.key ? 'border-moss bg-moss text-moss-ink' : 'border-line hover:bg-surface-2'}`}
              >
                {f.text}
              </button>
            ))}
          </div>
        </div>
        {recs.isLoading && <LoadingBlock label="Loading suggestions" />}
        {recs.error && <ErrorState error={recs.error} onRetry={() => recs.refetch()} />}
        {recs.data?.total === 0 && (
          <EmptyState title={filter === 'open' ? 'Nothing needs attention' : `No ${filter} suggestions`}>
            {filter === 'open' ? 'Suggestions appear after observations are recorded, or when the checks run.' : 'They will be listed here once there are some.'}
          </EmptyState>
        )}
        <ul className="space-y-2">{recs.data?.items.map((r) => <RecommendationCard key={r.id} rec={r} ws={ws} canDecide={canDecide} />)}</ul>
      </section>

      <section aria-labelledby="history">
        <h2 id="history" className="mb-2 font-semibold">Run history</h2>
        {runs.isLoading && <LoadingBlock label="Loading run history" />}
        {runs.error && <ErrorState error={runs.error} onRetry={() => runs.refetch()} />}
        {runs.data?.total === 0 && <EmptyState title="No runs yet">The agent runs on a schedule; you can also run it now.</EmptyState>}
        <ul className="space-y-2">{runs.data?.items.map((r) => <RunRow key={r.id} run={r} />)}</ul>
      </section>

      <section aria-labelledby="rules">
        <h2 id="rules" className="mb-2 font-semibold">Rules in force</h2>
        {rules.isLoading && <LoadingBlock label="Loading rules" />}
        <ul className="space-y-2">
          {rules.data?.map((r) => (
            <li key={r.key} className="rounded-lg border border-line bg-surface p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <code className="font-medium">{r.key}</code>
                {r.version != null && <span className="text-xs text-ink-3">version {r.version}</span>}
                <MethodBadge method={r.method as 'rule' | 'statistical'} />
              </div>
              <p className="mt-1 text-ink-2">{r.description}</p>
              <p className="mt-1 text-xs text-ink-3">{Object.entries(r.parameters).map(([k, v]) => `${label(k)}: ${v}`).join(' · ')}</p>
            </li>
          ))}
        </ul>
        {canDecide && <p className="mt-2 text-xs text-ink-3">Thresholds and the schedule come from workspace settings under <code>agent</code>.</p>}
      </section>
    </div>
  )
}
