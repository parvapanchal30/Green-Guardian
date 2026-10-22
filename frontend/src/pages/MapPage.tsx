import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { MapFeature, MapFilter } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { AssetMap } from '../components/AssetMap'
import { HealthChip, PageHeader, btn, btnPrimary, input } from '../components/domain'
import { StatusChip } from '../components/StatusChip'
import { EmptyState, ErrorState, LoadingBlock } from '../components/states'
import { useI18n, type TKey } from '../i18n'
import { useLocations, useMapLayer, useMapLayers } from '../lib/slice'

// Health bands reuse the health chip words; the rest are map-specific.
const CHIPS: { key: MapFilter; text: TKey }[] = [
  { key: 'all', text: 'map.chip.all' },
  { key: 'healthy', text: 'health.healthy' },
  { key: 'at_risk', text: 'health.at_risk' },
  { key: 'critical', text: 'health.critical' },
  { key: 'open_issues', text: 'map.chip.open_issues' },
  { key: 'tasks', text: 'map.chip.tasks' },
]
const KINDS = ['tree', 'plant', 'shrub', 'crop_batch', 'other']
const isFilter = (v: string | null): v is MapFilter => CHIPS.some((c) => c.key === v)

export function MapPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const { t, te } = useI18n()
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

  return (
    <div className="space-y-4">
      <PageHeader title={t('map.title')} subtitle={t(workspace.mode === 'agricultural_production' ? 'map.subtitle.agricultural_production' : 'map.subtitle.green_management')} />

      <div className="flex flex-wrap items-end gap-3">
        <div role="group" aria-label={t('map.filterAssets')} className="flex flex-wrap gap-2">
          {CHIPS.map((c) => (
            <button key={c.key} type="button" aria-pressed={filter === c.key} onClick={() => set('filter', c.key)}
              className={`rounded-full border px-3 py-1 text-sm ${filter === c.key ? 'border-ink bg-ink text-canvas' : 'border-line bg-surface hover:bg-surface-2'}`}>
              {t(c.text)}{fc && <span className="ml-1 opacity-75">{fc.counts[c.key === 'all' ? 'all' : c.key]}</span>}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1 text-sm">{t('map.location')}
          <select aria-label={t('map.filterLocation')} value={locationId} onChange={(e) => set('location', e.target.value)} className={input}>
            <option value="">{t('map.all')}</option>
            {locations.data?.items.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1 text-sm">{t('map.type')}
          <select aria-label={t('map.filterType')} value={kind} onChange={(e) => set('kind', e.target.value)} className={input}>
            <option value="">{t('map.all')}</option>
            {KINDS.map((k) => <option key={k} value={k}>{te('kind', k)}</option>)}
          </select>
        </label>
      </div>

      {q.isLoading && <LoadingBlock label={t('map.loading')} />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}

      {fc && fc.counts.all === 0 && (
        <EmptyState title={fc.counts.unlocated > 0 ? t('map.noLocated') : t('map.noAssets')}
          action={<Link to={`/w/${ws}/assets`} className="text-moss underline">{fc.counts.unlocated > 0 ? t('map.addCoords') : t('map.register')}</Link>}>
          {fc.counts.unlocated > 0
            ? t('map.unlocatedBody', { n: fc.counts.unlocated })
            : t('map.emptyBody')}
        </EmptyState>
      )}

      {fc && fc.counts.all > 0 && (
        <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
          <div className="space-y-2">
            <AssetMap features={fc.features} bbox={fc.bbox} selectedId={selectedId} onSelect={setSelectedId} />
            <p className="text-xs text-ink-3">
              {t('map.legend')}
              {fc.counts.unlocated > 0 && t('map.unlocatedNote', { n: fc.counts.unlocated })}
              {fc.truncated && t('map.truncated')}
            </p>
            {fc.features.length === 0 && <p role="status" className="text-sm text-ink-2">{t('map.noMatch')}</p>}
          </div>

          <aside aria-label={t('map.selected')} className="space-y-3">
            {selected ? (
              <div className="rounded-lg border border-line bg-surface p-3">
                <h2 className="text-lg font-semibold">{selected.properties.label}</h2>
                <p className="text-sm text-ink-2">
                  {te('kind', selected.properties.kind)}{selected.properties.species ? ` · ${selected.properties.species}` : ''}
                  {selected.properties.location_name ? ` · ${selected.properties.location_name}` : ''}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <HealthChip band={selected.properties.health_band} score={selected.properties.health_score} />
                  <StatusChip tone={selected.properties.open_issue_count ? 'critical' : 'neutral'}>{t('map.openIssues', { n: selected.properties.open_issue_count })}</StatusChip>
                  <StatusChip tone={selected.properties.open_task_count ? 'building' : 'neutral'}>{t('map.openTasks', { n: selected.properties.open_task_count })}</StatusChip>
                </div>
                {selected.properties.position_source === 'location' && <p className="mt-2 text-xs text-ink-3">{t('map.atLocationCentre')}</p>}
                <div className="mt-3 flex gap-2">
                  <Link to={`/w/${ws}/assets/${selected.properties.asset_id}`} className={btnPrimary}>{t('map.openProfile')}</Link>
                  <button type="button" className={btn} onClick={() => setSelectedId(null)}>{t('map.clear')}</button>
                </div>
                <p className="mt-2 text-xs text-ink-3">{t('map.profileHint')}</p>
              </div>
            ) : (
              <p className="rounded-lg border border-dashed border-line p-3 text-sm text-ink-2">{t('map.selectHint')}</p>
            )}

            <div>
              <h2 className="mb-1 text-sm font-semibold">{t('map.assetsCount', { n: fc.features.length })}</h2>
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
          <h2 id="layers" className="mb-1 text-sm font-semibold">{t('map.layers')}</h2>
          <ul className="flex flex-wrap gap-2 text-sm">
            <li><StatusChip tone="live">{t('map.live')}</StatusChip> {t('map.bioAssets')}</li>
            {planned.map((l) => (
              <li key={l.key} title={l.requires ? t('map.needs', { what: l.requires }) : undefined}>
                <StatusChip tone="soon">{t('map.planned', { stage: l.stage.toUpperCase() })}</StatusChip> <span className="text-ink-2">{l.label}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
