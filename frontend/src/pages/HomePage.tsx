import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { RecommendationCard } from '../components/RecommendationCard'
import { StatusChip } from '../components/StatusChip'
import { EmptyState, ErrorState, LoadingBlock } from '../components/states'
import { input } from '../components/domain'
import { atLeast, fmtDateTime } from '../lib/format'
import { useDashboard, useLocations, useRecommendations } from '../lib/slice'
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

const KINDS = ['tree', 'plant', 'shrub', 'crop_batch', 'other']

export function HomePage() {
  const { ws, workspace, capabilities } = useWorkspaceCtx()
  const v = VOCABULARY[workspace.mode]
  const [locationId, setLocationId] = useState('')
  const [kind, setKind] = useState('')
  const locations = useLocations(ws)
  const dash = useDashboard(ws, { location_id: locationId || undefined, kind: kind || undefined })
  const recs = useRecommendations(ws)
  const d = dash.data
  const canDecide = atLeast(workspace.role, 'manager')
  const filtered = Boolean(locationId || kind)

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{workspace.name}</h1>
        <p className="text-ink-2">{v.modeLabel} · {v.audience}</p>
      </header>

      <section aria-labelledby="state">
        <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
          <h2 id="state" className="text-lg font-semibold">Current state</h2>
          <div className="flex flex-wrap gap-2 text-sm">
            <label className="flex items-center gap-1">Location
              <select aria-label="Filter by location" value={locationId} onChange={(e) => setLocationId(e.target.value)} className={input}>
                <option value="">All</option>
                {locations.data?.items.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-1">Type
              <select aria-label="Filter by type" value={kind} onChange={(e) => setKind(e.target.value)} className={input}>
                <option value="">All</option>
                {KINDS.map((k) => <option key={k} value={k}>{k.replace('_', ' ')}</option>)}
              </select>
            </label>
          </div>
        </div>
        {dash.isLoading && <LoadingBlock label="Loading dashboard" />}
        {dash.error && <ErrorState error={dash.error} onRetry={() => dash.refetch()} />}
        {d && d.assets.total === 0 && (
          <EmptyState title={filtered ? 'No assets match these filters' : 'No assets yet'} action={!filtered && atLeast(workspace.role, 'worker') ? <Link to={`/w/${ws}/assets`} className="text-moss underline">Register the first asset</Link> : undefined}>
            {filtered ? 'Clear a filter to see the rest of the workspace.' : 'Register trees, plants or crop batches to see their health, issues and tasks here.'}
          </EmptyState>
        )}
        {d && d.assets.total > 0 && (
          <div className="space-y-4">
            <ul className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <Tile name="Assets" value={String(d.assets.total)} />
              <Tile name="Healthy" value={String(d.assets.health.healthy)} />
              <Tile name="At risk" value={String(d.assets.health.at_risk)} />
              <Tile name="Critical" value={String(d.assets.health.critical)} />
              <Tile name="Open issues" value={String(d.work.open_issues)} />
              <Tile name="Open tasks" value={String(d.work.open_tasks)} />
              {d.assets.health.unknown > 0 && <Tile name="No health data" value={String(d.assets.health.unknown)} hint="Not observed yet" />}
            </ul>
            <ul aria-label="Work needing attention" className="grid gap-3 sm:grid-cols-3">
              <Tile name="Overdue tasks" value={String(d.work.overdue_tasks)} hint={`${d.work.tasks_due_next_7_days} more due in 7 days`} />
              <Tile name="Inspections due" value={String(d.work.inspections_due)} hint={`No observation in ${d.work.inspection_interval_days} days`} />
              <Tile name="Suggestions to review" value={String(d.work.open_recommendations)} />
            </ul>
          </div>
        )}
        {d && (
          <details className="mt-3 text-sm text-ink-2">
            <summary className="cursor-pointer">{d.kpis.map((k) => k.label).join(' → ')}</summary>
            <ul className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {d.kpis.map((k) => (
                <li key={k.key} className="rounded border border-line p-2">
                  <span className="font-medium">{k.label}</span>
                  {k.available
                    ? <span className="block text-ink"><span className="font-semibold">{k.value}{k.unit}</span> <span className="text-xs text-ink-3">{k.basis}</span></span>
                    : <span className="block text-xs text-ink-3">{k.reason}</span>}
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>

      {d && d.recent_activity.length > 0 && (
        <section aria-labelledby="activity">
          <h2 id="activity" className="mb-2 text-lg font-semibold">Recent activity</h2>
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface text-sm">
            {d.recent_activity.map((a) => (
              <li key={`${a.type}-${a.ref_id}-${a.at}`} className="flex flex-wrap items-baseline justify-between gap-x-3 p-2">
                <span>
                  <Link className="text-moss underline" to={a.type === 'issue' ? `/w/${ws}/issues/${a.ref_id}` : a.asset_id ? `/w/${ws}/assets/${a.asset_id}` : `/w/${ws}/tasks`}>{a.title}</Link>
                  {a.detail && <span className="text-ink-2"> · {a.detail}</span>}
                </span>
                <time className="text-xs text-ink-3" dateTime={a.at}>{fmtDateTime(a.at)}</time>
              </li>
            ))}
          </ul>
        </section>
      )}

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
