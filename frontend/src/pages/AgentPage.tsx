import { useState } from 'react'
import type { AgentRunRecord } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { MethodBadge, PageHeader, btnPrimary } from '../components/domain'
import { RecommendationCard } from '../components/RecommendationCard'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { StatusChip } from '../components/StatusChip'
import { useI18n, type I18n } from '../i18n'
import { atLeast } from '../lib/format'
import { useAgentRules, useAgentRuns, useRecommendations, useRunAgent } from '../lib/slice'

const FILTERS = ['open', 'accepted', 'dismissed', 'expired'] as const
type Filter = (typeof FILTERS)[number]

const STATUS_TONE = { succeeded: 'live', failed: 'critical', running: 'building' } as const

/** What a run could not do, in words, so an empty result is never mistaken for "all clear". */
function runNotes(run: AgentRunRecord, { t, te }: Pick<I18n, 't' | 'te'>): string[] {
  const notes: string[] = []
  const skipped = run.diagnostics.skipped ?? {}
  for (const [reason, n] of Object.entries(skipped)) notes.push(`${n} × ${te('skipReason', reason).toLowerCase()}`)
  const w = run.diagnostics.weather
  if (w?.requested && (w.unavailable ?? 0) > 0) notes.push(t('agent.weatherUnavailable', { n: w.unavailable ?? 0 }))
  return notes
}

function RunRow({ run }: { run: AgentRunRecord }) {
  const i18n = useI18n()
  const { t, te, fmt } = i18n
  const notes = runNotes(run, i18n)
  return (
    <li className="rounded-lg border border-line bg-surface p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip tone={STATUS_TONE[run.status]}>{te('agent.runStatus', run.status)}</StatusChip>
        <StatusChip tone="neutral">{run.trigger === 'scheduled' ? t('agent.scheduled') : t('agent.manual')}</StatusChip>
        <span>{fmt.dateTime(run.started_at)}</span>
        {run.duration_s != null && <span className="text-xs text-ink-3">{run.duration_s.toFixed(1)} s</span>}
      </div>
      {run.status === 'failed' ? (
        <p role="alert" className="mt-1 text-critical">{run.error ?? t('agent.runFailed')}</p>
      ) : (
        <p className="mt-1 text-ink-2">
          {t('agent.runSummary', { assets: run.evaluated_assets, created: run.recommendations_created, expired: run.recommendations_expired })}
        </p>
      )}
      {notes.length > 0 && <p className="mt-1 text-xs text-ink-3">{t('agent.skipped', { notes: notes.join(' · ') })}</p>}
    </li>
  )
}

export function AgentPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const { t, te } = useI18n()
  const [filter, setFilter] = useState<Filter>('open')
  const rules = useAgentRules(ws)
  const recs = useRecommendations(ws, { status: filter, limit: 25 })
  const runs = useAgentRuns(ws, 10)
  const run = useRunAgent(ws)
  const canDecide = atLeast(workspace.role, 'manager')

  return (
    <div className="space-y-6">
      <PageHeader title={t('agent.title')} subtitle={t('agent.subtitle')}>
        <StatusChip tone="live">{t('agent.technique')}</StatusChip>
        {canDecide && <button type="button" className={btnPrimary} disabled={run.isPending} onClick={() => run.mutate(undefined as never)}>{run.isPending ? t('agent.checking') : t('agent.runNow')}</button>}
      </PageHeader>

      <p className="max-w-prose rounded-lg border border-line bg-surface p-3 text-sm text-ink-2">
        {t('agent.about1')} {t('agent.about2')} {t('agent.about3')}
      </p>

      {run.data && (
        <p role="status" className="text-sm text-ink-2">
          {t('agent.ranResult', { assets: run.data.evaluated_assets, created: run.data.created.length, expired: run.data.expired })}
        </p>
      )}
      {run.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(run.error)}</p>}

      <section aria-labelledby="suggestions">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 id="suggestions" className="font-semibold">{t('agent.suggestions')}</h2>
          <div role="group" aria-label={t('agent.suggestionStatus')} className="flex gap-1">
            {FILTERS.map((f) => (
              <button
                key={f}
                type="button"
                aria-pressed={filter === f}
                onClick={() => setFilter(f)}
                className={`rounded border px-2 py-1 text-xs ${filter === f ? 'border-moss bg-moss text-moss-ink' : 'border-line hover:bg-surface-2'}`}
              >
                {te('rec.status', f)}
              </button>
            ))}
          </div>
        </div>
        {recs.isLoading && <LoadingBlock label={t('agent.loadingSuggestions')} />}
        {recs.error && <ErrorState error={recs.error} onRetry={() => recs.refetch()} />}
        {recs.data?.total === 0 && (
          <EmptyState title={filter === 'open' ? t('agent.nothing') : t('agent.noneOfStatus', { status: te('rec.status', filter).toLowerCase() })}>
            {filter === 'open' ? t('agent.emptyOpen') : t('agent.emptyOther')}
          </EmptyState>
        )}
        <ul className="space-y-2">{recs.data?.items.map((r) => <RecommendationCard key={r.id} rec={r} ws={ws} canDecide={canDecide} />)}</ul>
      </section>

      <section aria-labelledby="history">
        <h2 id="history" className="mb-2 font-semibold">{t('agent.runHistory')}</h2>
        {runs.isLoading && <LoadingBlock label={t('agent.loadingRuns')} />}
        {runs.error && <ErrorState error={runs.error} onRetry={() => runs.refetch()} />}
        {runs.data?.total === 0 && <EmptyState title={t('agent.noRuns')}>{t('agent.noRunsBody')}</EmptyState>}
        <ul className="space-y-2">{runs.data?.items.map((r) => <RunRow key={r.id} run={r} />)}</ul>
      </section>

      <section aria-labelledby="rules">
        <h2 id="rules" className="mb-2 font-semibold">{t('agent.rules')}</h2>
        {rules.isLoading && <LoadingBlock label={t('agent.loadingRules')} />}
        <ul className="space-y-2">
          {rules.data?.map((r) => (
            <li key={r.key} className="rounded-lg border border-line bg-surface p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <code className="font-medium">{r.key}</code>
                {r.version != null && <span className="text-xs text-ink-3">{t('agent.version', { n: r.version })}</span>}
                <MethodBadge method={r.method as 'rule' | 'statistical'} />
              </div>
              <p className="mt-1 text-ink-2">{r.description}</p>
              <p className="mt-1 text-xs text-ink-3">{Object.entries(r.parameters).map(([k, v]) => `${te('ruleParam', k)}: ${v}`).join(' · ')}</p>
            </li>
          ))}
        </ul>
        {canDecide && <p className="mt-2 text-xs text-ink-3">{t('agent.settingsHint')} <code>agent</code>.</p>}
      </section>
    </div>
  )
}
