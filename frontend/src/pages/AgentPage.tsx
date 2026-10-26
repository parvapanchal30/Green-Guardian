import { useState } from 'react'
import type { AgentRunRecord } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { MethodBadge, PageHeader, btnPrimary } from '../components/domain'
import { RecommendationCard } from '../components/RecommendationCard'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { StatusChip } from '../components/StatusChip'
import { Icon } from '../components/icons'
import { Card, SectionHeading, Segmented, Tag } from '../components/ui'
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
    <li className="border-b border-line-soft py-2 text-sm last:border-0">
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
  const [latest, ...older] = runs.data?.items ?? []

  return (
    <div className="flex flex-col gap-4">
      <PageHeader eyebrow={t('eyebrow.insight')} title={t('agent.title')} subtitle={t('agent.subtitle')}>
        <Tag tone="moss">{t('agent.technique')}</Tag>
        {canDecide && (
          <button type="button" className={btnPrimary} disabled={run.isPending} onClick={() => run.mutate(undefined as never)}>
            <Icon name="agent" size={16} />
            {run.isPending ? t('agent.checking') : t('agent.runNow')}
          </button>
        )}
      </PageHeader>

      <p className="max-w-prose text-sm text-ink-2">{t('agent.about1')} {t('agent.about2')} {t('agent.about3')}</p>

      {run.data && (
        <p role="status" className="rounded-md border border-moss/40 bg-moss-soft px-3 py-2 text-sm">
          {t('agent.ranResult', { assets: run.data.evaluated_assets, created: run.data.created.length, expired: run.data.expired })}
        </p>
      )}
      {run.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(run.error)}</p>}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <section aria-labelledby="suggestions" className="flex flex-col gap-3">
          <SectionHeading id="suggestions" title={t('agent.suggestions')}>
            <Segmented label={t('agent.suggestionStatus')} value={filter} onChange={setFilter} options={FILTERS.map((f) => ({ value: f, label: te('rec.status', f) }))} />
          </SectionHeading>
          {recs.isLoading && <LoadingBlock label={t('agent.loadingSuggestions')} />}
          {recs.error && <ErrorState error={recs.error} onRetry={() => recs.refetch()} />}
          {recs.data?.total === 0 && (
            <EmptyState icon="agent" title={filter === 'open' ? t('agent.nothing') : t('agent.noneOfStatus', { status: te('rec.status', filter).toLowerCase() })}>
              {filter === 'open' ? t('agent.emptyOpen') : t('agent.emptyOther')}
            </EmptyState>
          )}
          <ul className="flex flex-col gap-2">{recs.data?.items.map((r) => <RecommendationCard key={r.id} rec={r} ws={ws} canDecide={canDecide} />)}</ul>
        </section>

        <aside className="flex flex-col gap-3.5">
          <Card className="p-4">
            <section aria-labelledby="rules">
              <SectionHeading id="rules" title={t('agent.rules')} />
              {rules.isLoading && <LoadingBlock label={t('agent.loadingRules')} />}
              <ul className="flex flex-col">
                {rules.data?.map((r) => (
                  <li key={r.key} className="flex flex-col gap-1 border-b border-line-soft py-2.5 text-sm last:border-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <b>{te('ruleName', r.key)}</b>
                      <span className="ml-auto"><MethodBadge method={r.method as 'rule' | 'statistical'} /></span>
                    </div>
                    <p className="text-ink-2">{r.description}</p>
                    <p className="font-mono text-[11px] text-ink-2">
                      {r.key}{r.version != null && <> · <span>{t('agent.version', { n: r.version })}</span></>}
                    </p>
                    {Object.keys(r.parameters).length > 0 && (
                      <p className="text-xs text-ink-2">{Object.entries(r.parameters).map(([k, v]) => `${te('ruleParam', k)}: ${v}`).join(' · ')}</p>
                    )}
                  </li>
                ))}
              </ul>
              {canDecide && <p className="mt-2 text-xs text-ink-2">{t('agent.settingsHint')} <code>agent</code>.</p>}
            </section>
          </Card>

          <Card className="p-4">
            <section aria-labelledby="history">
              <SectionHeading id="history" title={t('agent.runHistory')} />
              {runs.isLoading && <LoadingBlock label={t('agent.loadingRuns')} />}
              {runs.error && <ErrorState error={runs.error} onRetry={() => runs.refetch()} />}
              {runs.data?.total === 0 && <p className="text-sm text-ink-2">{t('agent.noRuns')} {t('agent.noRunsBody')}</p>}
              {latest && <ul className="flex flex-col"><RunRow run={latest} /></ul>}
              {older.length > 0 && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-sm text-ink-2">{t('agent.olderRuns', { count: older.length })}</summary>
                  <ul className="mt-1 flex flex-col">{older.map((r) => <RunRow key={r.id} run={r} />)}</ul>
                </details>
              )}
            </section>
          </Card>
        </aside>
      </div>
    </div>
  )
}
