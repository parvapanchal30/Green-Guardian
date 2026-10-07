import { Link } from 'react-router-dom'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { RecommendationCard } from '../components/RecommendationCard'
import { StatusChip } from '../components/StatusChip'
import { EmptyState, ErrorState, LoadingBlock } from '../components/states'
import { atLeast } from '../lib/format'
import { useCounts, useRecommendations } from '../lib/slice'
import { VOCABULARY } from '../lib/vocabulary'

function Tile({ name, value, hint }: { name: string; value: string; hint?: string }) {
  return (
    <li className="rounded-lg border border-line bg-surface p-3">
      <p className="text-sm text-ink-2">{name}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
      {hint && <p className="mt-1 text-xs text-ink-3">{hint}</p>}
    </li>
  )
}

export function HomePage() {
  const { ws, workspace, capabilities } = useWorkspaceCtx()
  const v = VOCABULARY[workspace.mode]
  const counts = useCounts(ws)
  const recs = useRecommendations(ws)
  const c = counts.data
  const canDecide = atLeast(workspace.role, 'manager')
  // KPIs that cannot be computed from recorded data yet stay explicit about it.
  const notYet: Record<string, string> = { Survival: 'Needs planting and loss records', Canopy: 'Needs canopy measurements', Coverage: 'Needs zone areas', Growth: 'Needs growth records', Yield: 'Estimates are planned (V2)', Harvest: 'Estimates are planned (V2)', Revenue: 'Needs yield and price data' }

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{workspace.name}</h1>
        <p className="text-ink-2">{v.modeLabel} · {v.audience}</p>
      </header>

      <section aria-labelledby="state">
        <h2 id="state" className="mb-2 text-lg font-semibold">Current state</h2>
        {counts.isLoading && <LoadingBlock label="Loading counts" />}
        {counts.error && <ErrorState error={counts.error} onRetry={() => counts.refetch()} />}
        {c && (
          c.assets === 0 ? (
            <EmptyState title="No assets yet" action={atLeast(workspace.role, 'worker') ? <Link to={`/w/${ws}/assets`} className="text-moss underline">Register the first asset</Link> : undefined}>
              Register trees, plants or crop batches to see their health, issues and tasks here.
            </EmptyState>
          ) : (
            <ul className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <Tile name="Assets" value={String(c.assets)} />
              <Tile name="Healthy" value={String(c.healthy)} />
              <Tile name="At risk" value={String(c.atRisk)} />
              <Tile name="Critical" value={String(c.critical)} />
              <Tile name="Open issues" value={String(c.openIssues)} />
              <Tile name="Open tasks" value={String(c.openTasks)} />
              {c.unknown > 0 && <Tile name="No health data" value={String(c.unknown)} hint="Not observed yet" />}
            </ul>
          )
        )}
        <details className="mt-3 text-sm text-ink-2">
          <summary className="cursor-pointer">{v.kpis.join(' → ')}: what is not measured yet</summary>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {v.kpis.map((k) => <li key={k} className="rounded border border-line p-2"><span className="font-medium">{k}</span><span className="block text-xs text-ink-3">{notYet[k] ?? 'Computed from recorded observations'}</span></li>)}
          </ul>
        </details>
      </section>

      <section aria-labelledby="attention">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 id="attention" className="text-lg font-semibold">Needs attention</h2>
          <Link to={`/w/${ws}/ai/agent`} className="text-sm text-moss underline">Botanical Operations Agent</Link>
        </div>
        {recs.isLoading && <LoadingBlock label="Loading suggestions" />}
        {recs.error && <ErrorState error={recs.error} onRetry={() => recs.refetch()} />}
        {recs.data?.total === 0 && <EmptyState title="Nothing to review">Rule-based suggestions appear here after observations are recorded, each with the reason it was raised.</EmptyState>}
        <ul className="space-y-2">{recs.data?.items.map((r) => <RecommendationCard key={r.id} rec={r} ws={ws} canDecide={canDecide} />)}</ul>
      </section>

      <section aria-labelledby="caps">
        <h2 id="caps" className="mb-2 text-lg font-semibold">What is live in this workspace</h2>
        {!capabilities ? <LoadingBlock label="Loading capabilities" /> : (
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Capabilities and their availability</caption>
              <thead className="border-b border-line text-ink-2"><tr><th className="p-2 font-medium">Capability</th><th className="p-2 font-medium">Technique</th><th className="p-2 font-medium">Status</th></tr></thead>
              <tbody>
                {capabilities.map((cap) => (
                  <tr key={cap.key} className="border-b border-line last:border-0">
                    <td className="p-2">{cap.label}</td><td className="p-2 text-ink-2">{cap.technique}</td>
                    <td className="p-2">{cap.available ? <StatusChip tone="live">Live</StatusChip> : <StatusChip tone={cap.stage === 'mvp' ? 'building' : 'soon'}>{cap.stage === 'mvp' ? 'In development' : `Planned · ${cap.stage.toUpperCase()}`}</StatusChip>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
