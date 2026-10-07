import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { MapFeature, MapFilter } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { AssetMap } from '../components/AssetMap'
import { HealthChip, PageHeader, btn, btnPrimary, input } from '../components/domain'
import { StatusChip } from '../components/StatusChip'
import { EmptyState, ErrorState, LoadingBlock } from '../components/states'
import { label } from '../lib/format'
import { useLocations, useMapLayer, useMapLayers } from '../lib/slice'

const CHIPS: { key: MapFilter; text: string }[] = [
  { key: 'all', text: 'All' },
  { key: 'healthy', text: 'Healthy' },
  { key: 'at_risk', text: 'At risk' },
  { key: 'critical', text: 'Critical' },
  { key: 'open_issues', text: 'Open issues' },
  { key: 'tasks', text: 'Tasks' },
]
const KINDS = ['tree', 'plant', 'shrub', 'crop_batch', 'other']
const isFilter = (v: string | null): v is MapFilter => CHIPS.some((c) => c.key === v)

export function MapPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const [params, setParams] = useSearchParams()
  const filter: MapFilter = isFilter(params.get('filter')) ? (params.get('filter') as MapFilter) : 'all'
  const locationId = params.get('location') ?? ''
  const kind = params.get('kind') ?? ''
  const set = (k: string, v: string) => setParams((p) => { const n = new URLSearchParams(p); if (v && !(k === 'filter' && v === 'all')) n.set(k, v); else n.delete(k); return n }, { replace: true })

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const layers = useMapLayers(ws)
  const locations = useLocations(ws)
  const q = useMapLayer(ws, 'assets', { filter, location_id: locationId || undefined, kind: kind || undefined })
  const fc = q.data
  const selected: MapFeature | undefined = useMemo(() => fc?.features.find((f) => f.id === selectedId), [fc, selectedId])
  const planned = layers.data?.filter((l) => !l.available) ?? []
  const noun = workspace.mode === 'agricultural_production' ? 'crop batches and trees' : 'trees and plants'

  return (
    <div className="space-y-4">
      <PageHeader title="Map" subtitle={`Where your ${noun} are, and which ones need attention.`} />

      <div className="flex flex-wrap items-end gap-3">
        <div role="group" aria-label="Filter assets" className="flex flex-wrap gap-2">
          {CHIPS.map((c) => (
            <button key={c.key} type="button" aria-pressed={filter === c.key} onClick={() => set('filter', c.key)}
              className={`rounded-full border px-3 py-1 text-sm ${filter === c.key ? 'border-ink bg-ink text-canvas' : 'border-line bg-surface hover:bg-surface-2'}`}>
              {c.text}{fc && <span className="ml-1 opacity-75">{fc.counts[c.key === 'all' ? 'all' : c.key]}</span>}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1 text-sm">Location
          <select aria-label="Filter by location" value={locationId} onChange={(e) => set('location', e.target.value)} className={input}>
            <option value="">All</option>
            {locations.data?.items.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1 text-sm">Type
          <select aria-label="Filter by type" value={kind} onChange={(e) => set('kind', e.target.value)} className={input}>
            <option value="">All</option>
            {KINDS.map((k) => <option key={k} value={k}>{label(k)}</option>)}
          </select>
        </label>
      </div>

      {q.isLoading && <LoadingBlock label="Loading map" />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}

      {fc && fc.counts.all === 0 && (
        <EmptyState title={fc.counts.unlocated > 0 ? 'No asset has a location on the map yet' : 'No assets to show'}
          action={<Link to={`/w/${ws}/assets`} className="text-moss underline">{fc.counts.unlocated > 0 ? 'Add coordinates to assets' : 'Register an asset'}</Link>}>
          {fc.counts.unlocated > 0
            ? `${fc.counts.unlocated} asset(s) exist but have no coordinates and no located zone, so they cannot be drawn.`
            : 'Register assets with coordinates, or place them in a zone that has coordinates.'}
        </EmptyState>
      )}

      {fc && fc.counts.all > 0 && (
        <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
          <div className="space-y-2">
            <AssetMap features={fc.features} bbox={fc.bbox} selectedId={selectedId} onSelect={setSelectedId} />
            <p className="text-xs text-ink-3">
              ● healthy · ▲ at risk · ■ critical · ○ no health data · red dot = open issue.
              {fc.counts.unlocated > 0 && ` ${fc.counts.unlocated} asset(s) have no coordinates and are not drawn.`}
              {fc.truncated && ' Showing the first results only; narrow the filters to see the rest.'}
            </p>
            {fc.features.length === 0 && <p role="status" className="text-sm text-ink-2">No assets match this filter. Try All.</p>}
          </div>

          <aside aria-label="Selected asset" className="space-y-3">
            {selected ? (
              <div className="rounded-lg border border-line bg-surface p-3">
                <h2 className="text-lg font-semibold">{selected.properties.label}</h2>
                <p className="text-sm text-ink-2">
                  {label(selected.properties.kind)}{selected.properties.species ? ` · ${selected.properties.species}` : ''}
                  {selected.properties.location_name ? ` · ${selected.properties.location_name}` : ''}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <HealthChip band={selected.properties.health_band} score={selected.properties.health_score} />
                  <StatusChip tone={selected.properties.open_issue_count ? 'critical' : 'neutral'}>{selected.properties.open_issue_count} open issue(s)</StatusChip>
                  <StatusChip tone={selected.properties.open_task_count ? 'building' : 'neutral'}>{selected.properties.open_task_count} open task(s)</StatusChip>
                </div>
                {selected.properties.position_source === 'location' && <p className="mt-2 text-xs text-ink-3">Shown at the centre of its location (no own coordinates).</p>}
                <div className="mt-3 flex gap-2">
                  <Link to={`/w/${ws}/assets/${selected.properties.asset_id}`} className={btnPrimary}>Open asset profile</Link>
                  <button type="button" className={btn} onClick={() => setSelectedId(null)}>Clear</button>
                </div>
                <p className="mt-2 text-xs text-ink-3">Record an observation, open an issue or create a task from the profile.</p>
              </div>
            ) : (
              <p className="rounded-lg border border-dashed border-line p-3 text-sm text-ink-2">Select an asset on the map or in the list to see its state.</p>
            )}

            <div>
              <h2 className="mb-1 text-sm font-semibold">Assets ({fc.features.length})</h2>
              <ul className="max-h-64 divide-y divide-line overflow-y-auto rounded-lg border border-line bg-surface text-sm">
                {fc.features.map((f) => (
                  <li key={f.id}>
                    <button type="button" aria-current={f.id === selectedId} onClick={() => setSelectedId(f.id)}
                      className={`flex w-full items-center justify-between gap-2 p-2 text-left hover:bg-surface-2 ${f.id === selectedId ? 'bg-surface-2' : ''}`}>
                      <span>{f.properties.label}</span>
                      <HealthChip band={f.properties.health_band} />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </aside>
        </div>
      )}

      {planned.length > 0 && (
        <section aria-labelledby="layers">
          <h2 id="layers" className="mb-1 text-sm font-semibold">Map layers</h2>
          <ul className="flex flex-wrap gap-2 text-sm">
            <li><StatusChip tone="live">Live</StatusChip> Biological assets</li>
            {planned.map((l) => (
              <li key={l.key} title={l.requires ? `Needs: ${l.requires}` : undefined}>
                <StatusChip tone="soon">Planned · {l.stage.toUpperCase()}</StatusChip> <span className="text-ink-2">{l.label}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
