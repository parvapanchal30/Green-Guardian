import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { MethodBadge, PageHeader, btnPrimary } from '../components/domain'
import { RecommendationCard } from '../components/RecommendationCard'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { StatusChip } from '../components/StatusChip'
import { atLeast, label } from '../lib/format'
import { useAgentRules, useRecommendations, useRunAgent } from '../lib/slice'

export function AgentPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const rules = useAgentRules(ws)
  const recs = useRecommendations(ws)
  const run = useRunAgent(ws)
  const canDecide = atLeast(workspace.role, 'manager')

  return (
    <div className="space-y-6">
      <PageHeader title="Botanical Operations Agent" subtitle="Deterministic rules over recorded data. It suggests; a person decides.">
        <StatusChip tone="live">Rules + statistics</StatusChip>
        {canDecide && <button type="button" className={btnPrimary} disabled={run.isPending} onClick={() => run.mutate(undefined as never)}>{run.isPending ? 'Checking…' : 'Run checks now'}</button>}
      </PageHeader>

      <p className="max-w-prose rounded-lg border border-line bg-surface p-3 text-sm text-ink-2">
        This agent applies thresholds to what has been recorded. It does not use machine learning or a language model, and it never creates issues or tasks on its own.
        Prediction, recommendation engines and optimisation are planned for later versions and are shown as “Coming soon” elsewhere.
      </p>

      {run.data && <p role="status" className="text-sm text-ink-2">Checked {run.data.evaluated_assets} asset(s); {run.data.created.length} new suggestion(s).</p>}
      {run.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(run.error)}</p>}

      <section aria-labelledby="open">
        <h2 id="open" className="mb-2 font-semibold">Open suggestions</h2>
        {recs.isLoading && <LoadingBlock label="Loading suggestions" />}
        {recs.error && <ErrorState error={recs.error} onRetry={() => recs.refetch()} />}
        {recs.data?.total === 0 && <EmptyState title="Nothing needs attention">Suggestions appear after observations are recorded, or when you run the checks.</EmptyState>}
        <ul className="space-y-2">{recs.data?.items.map((r) => <RecommendationCard key={r.id} rec={r} ws={ws} canDecide={canDecide} />)}</ul>
      </section>

      <section aria-labelledby="rules">
        <h2 id="rules" className="mb-2 font-semibold">Rules in force</h2>
        {rules.isLoading && <LoadingBlock label="Loading rules" />}
        <ul className="space-y-2">
          {rules.data?.map((r) => (
            <li key={r.key} className="rounded-lg border border-line bg-surface p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2"><code className="font-medium">{r.key}</code><MethodBadge method={r.method as 'rule' | 'statistical'} /></div>
              <p className="mt-1 text-ink-2">{r.description}</p>
              <p className="mt-1 text-xs text-ink-3">{Object.entries(r.parameters).map(([k, v]) => `${label(k)}: ${v}`).join(' · ')}</p>
            </li>
          ))}
        </ul>
        {canDecide && <p className="mt-2 text-xs text-ink-3">Thresholds come from workspace settings under <code>agent</code>.</p>}
      </section>
    </div>
  )
}
