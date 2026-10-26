import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { MapFeature, MapFilter } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { AssetMap } from '../components/AssetMap'
import { HealthChip, PageHeader, btn, btnPrimary } from '../components/domain'
import { Icon } from '../components/icons'
import { Card, FilterBar, FilterSelect, SectionHeading } from '../components/ui'
import { atLeast } from '../lib/format'
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
/** Shapes repeat the health chips so bands are told apart without colour. */
const GLYPH: Partial<Record<MapFilter, { g: string; cls: string }>> = {
  healthy: { g: '●', cls: 'text-healthy' },
  at_risk: { g: '▲', cls: 'text-at-risk' },
  critical: { g: '■', cls: 'text-critical' },
}
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
  const canRecord = atLeast(workspace.role, 'worker')

  return (
    <div className="flex flex-col gap-4">
      <PageHeader eyebrow={t('eyebrow.monitor')} title={t('map.title')} subtitle={t(workspace.mode === 'agricultural_production' ? 'map.subtitle.agricultural_production' : 'map.subtitle.green_management')} />

      <FilterBar>
        <div role="group" aria-label={t('map.filterAssets')} className="flex flex-wrap gap-1.5">
          {CHIPS.map((c) => (
            <button key={c.key} type="button" aria-pressed={filter === c.key} onClick={() => set('filter', c.key)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[13.5px] ${filter === c.key ? 'border-ink bg-ink text-canvas' : 'border-line bg-surface hover:bg-surface-2'}`}>
              {GLYPH[c.key] && <span aria-hidden="true" className={`text-[0.7em] ${filter === c.key ? '' : GLYPH[c.key]!.cls}`}>{GLYPH[c.key]!.g}</span>}
              {t(c.text)}{fc && <span className="ml-0.5 font-mono text-xs opacity-75">{fc.counts[c.key === 'all' ? 'all' : c.key]}</span>}
            </button>
          ))}
        </div>
        <FilterSelect id="map-loc" label={t('map.filterLocation')} value={locationId} onChange={(v) => set('location', v)}>
          <option value="">{t('map.allPlaces')}</option>
          {locations.data?.items.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </FilterSelect>
        <FilterSelect id="map-kind" label={t('map.filterType')} value={kind} onChange={(v) => set('kind', v)}>
          <option value="">{t('assets.allTypes')}</option>
          {KINDS.map((k) => <option key={k} value={k}>{te('kind', k)}</option>)}
        </FilterSelect>
      </FilterBar>

      {q.isLoading && <LoadingBlock label={t('map.loading')} />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}

      {fc && fc.counts.all === 0 && (
        <EmptyState icon="map" title={fc.counts.unlocated > 0 ? t('map.noLocated') : t('map.noAssets')}
          action={<Link to={`/w/${ws}/assets`} className="text-moss underline">{fc.counts.unlocated > 0 ? t('map.addCoords') : t('map.register')}</Link>}>
          {fc.counts.unlocated > 0
            ? t('map.unlocatedBody', { n: fc.counts.unlocated })
            : t('map.emptyBody')}
        </EmptyState>
      )}

      {fc && fc.counts.all > 0 && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
          <div className="flex flex-col gap-2">
            <div className="overflow-hidden rounded-lg border border-line">
              <AssetMap features={fc.features} bbox={fc.bbox} selectedId={selectedId} onSelect={setSelectedId} />
            </div>
            <p className="text-xs text-ink-2">
              {t('map.legend')}
              {fc.counts.unlocated > 0 && t('map.unlocatedNote', { n: fc.counts.unlocated })}
              {fc.truncated && t('map.truncated')}
            </p>
            {fc.features.length === 0 && <p role="status" className="text-sm text-ink-2">{t('map.noMatch')}</p>}
          </div>

          <aside aria-label={t('map.selected')} className="flex flex-col gap-3">
            {selected ? (
              <Card className="flex flex-col gap-2 p-3.5 shadow-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <HealthChip band={selected.properties.health_band} score={selected.properties.health_score} />
                  <span className="text-[13px] text-ink-2">{te('kind', selected.properties.kind)}</span>
                </div>
                <h2 className="text-lg font-semibold">{selected.properties.label}</h2>
                <p className="text-[13px] text-ink-2">
                  {[selected.properties.species, selected.properties.location_name].filter(Boolean).join(' · ')}
                </p>
                <div className="flex flex-wrap gap-2">
                  <StatusChip tone={selected.properties.open_issue_count ? 'critical' : 'neutral'}>{t('map.openIssues', { n: selected.properties.open_issue_count })}</StatusChip>
                  <StatusChip tone={selected.properties.open_task_count ? 'building' : 'neutral'}>{t('map.openTasks', { n: selected.properties.open_task_count })}</StatusChip>
                </div>
                {selected.properties.position_source === 'location' && <p className="text-xs text-ink-2">{t('map.atLocationCentre')}</p>}
                <div className="mt-1 flex flex-wrap gap-2">
                  {canRecord && <Link to={`/w/${ws}/assets/${selected.properties.asset_id}#record`} className={btnPrimary}><Icon name="record" size={16} />{t('map.record')}</Link>}
                  <Link to={`/w/${ws}/assets/${selected.properties.asset_id}`} className={canRecord ? btn : btnPrimary}>{t('map.openProfile')}</Link>
                  <button type="button" className={`${btn} px-2`} aria-label={t('map.clear')} onClick={() => setSelectedId(null)}><Icon name="close" size={16} /></button>
                </div>
              </Card>
            ) : (
              <p className="rounded-lg border border-dashed border-line p-3 text-sm text-ink-2">{t('map.selectHint')}</p>
            )}

            <Card className="overflow-hidden">
              <h2 className="border-b border-line px-3 py-2.5 text-[17px] font-semibold">{t('map.assetsCount', { n: fc.features.length })}</h2>
              <ul className="max-h-80 overflow-y-auto text-sm">
                {fc.features.map((f) => (
                  <li key={f.id} className="border-b border-line-soft last:border-0">
                    <button type="button" aria-current={f.id === selectedId} onClick={() => setSelectedId(f.id)}
                      className={`flex w-full items-center gap-2.5 px-3 py-2 text-left hover:bg-surface-2 ${f.id === selectedId ? 'bg-moss-soft/60' : ''}`}>
                      <span className="flex min-w-0 flex-1 flex-col">
                        <b className="truncate">{f.properties.label}</b>
                        {f.properties.location_name && <span className="truncate text-xs text-ink-2">{f.properties.location_name}</span>}
                      </span>
                      <HealthChip band={f.properties.health_band} score={f.properties.health_score} />
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          </aside>
        </div>
      )}

      {planned.length > 0 && (
        <section aria-labelledby="layers">
          <SectionHeading id="layers" title={t('map.layers')} />
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
