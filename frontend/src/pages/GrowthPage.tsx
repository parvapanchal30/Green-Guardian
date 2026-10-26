import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { MethodBadge, PageHeader } from '../components/domain'
import { FilterBar, FilterSelect, LedgerTable, Segmented, StatTile, type LedgerColumn } from '../components/ui'
import { EmptyState, ErrorState, LoadingBlock } from '../components/states'
import { useI18n, type TKey } from '../i18n'
import { UNIT, useAssetGrowth, useGrowthMonitor, type GrowthMetric, type GrowthRow, type Measurement } from '../lib/monitor'

const METRICS: GrowthMetric[] = ['height_cm', 'girth_cm', 'canopy_m']
const SPANS = [3, 6, 12, 24] as const

/** A small line of recorded values (no interpolation beyond joining the measured points). */
function Spark({ points }: { points: number[] }) {
  if (points.length < 2) return null
  const lo = Math.min(...points)
  const hi = Math.max(...points)
  const span = hi - lo || 1
  const d = points.map((p, i) => `${(i / (points.length - 1)) * 100},${28 - ((p - lo) / span) * 24}`).join(' ')
  return (
    <svg viewBox="0 0 100 30" className="h-8 w-28 text-moss" aria-hidden="true" preserveAspectRatio="none">
      <polyline points={d} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

/** Measurements recorded for one asset (asset page). */
export function GrowthPanel({ ws, assetId }: { ws: string; assetId: string }) {
  const { t, fmt } = useI18n()
  const q = useAssetGrowth(ws, assetId)
  const rows: Measurement[] = q.data?.measurements ?? []
  if (q.isLoading) return <LoadingBlock label={t('mg.loading')} />
  return (
    <section aria-labelledby="growth">
      <h2 id="growth" className="mb-2 text-[19px] font-semibold">{t('mg.panelTitle')}</h2>
      {rows.length === 0 ? <p className="text-sm text-ink-3">{t('mg.noneAsset')}</p> : (
        <>
          <div className="mb-2 flex flex-wrap gap-4">
            {METRICS.map((m) => {
              const pts = rows.map((r) => r[m]).filter((v): v is number => v != null)
              return pts.length ? (
                <div key={m} className="text-sm">
                  <p className="text-xs text-ink-3">{t(`mg.metric.${m}` as TKey)}</p>
                  <p>{fmt.number(pts[pts.length - 1])} {UNIT[m]}</p>
                  <Spark points={pts} />
                </div>
              ) : null
            })}
          </div>
          <ol aria-label={t('mg.history')} className="space-y-0.5 text-xs text-ink-2">
            {[...rows].reverse().map((r) => (
              <li key={r.observation_id}>
                {fmt.date(r.observed_at)} · {METRICS.filter((m) => r[m] != null).map((m) => `${t(`mg.metric.${m}` as TKey)} ${fmt.number(r[m] ?? 0)} ${UNIT[m]}`).join(' · ')}
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  )
}

/** Growth between recorded measurements, per asset, over a period (ADR-076). */
export function GrowthPage() {
  const { ws } = useWorkspaceCtx()
  const { t, fmt } = useI18n()
  const [metric, setMetric] = useState<GrowthMetric>('height_cm')
  const [months, setMonths] = useState<number>(12)
  const q = useGrowthMonitor(ws, metric, months)
  const d = q.data
  const unit = UNIT[metric]

  const columns: LedgerColumn<GrowthRow>[] = [
    { key: 'asset', header: t('mg.asset'), primary: true, cell: (r) => <Link className="font-semibold text-ink hover:text-moss hover:underline" to={`/w/${ws}/assets/${r.asset_id}`}>{r.label}</Link> },
    { key: 'first', header: t('mg.first'), cell: (r) => <span>{fmt.number(r.first)} {unit} <span className="font-mono text-[11px] text-ink-3">{fmt.date(r.first_at)}</span></span> },
    { key: 'latest', header: t('mg.latest'), cell: (r) => <span>{fmt.number(r.latest)} {unit} <span className="font-mono text-[11px] text-ink-3">{fmt.date(r.latest_at)}</span></span> },
    {
      key: 'change', header: t('mg.change'),
      cell: (r) =>
        r.change != null ? (
          <b className={r.change > 0 ? 'text-healthy' : r.change < 0 ? 'text-critical' : ''}>{`${r.change > 0 ? '+' : ''}${fmt.number(r.change)} ${unit} (${fmt.number(r.change_pct ?? 0, { maximumFractionDigits: 1 })}%)`}</b>
        ) : <span className="text-ink-3">{t('mg.notYet')}</span>,
    },
    { key: 'year', header: t('mg.perYear'), numeric: true, cell: (r) => (r.per_year != null ? `${fmt.number(r.per_year, { maximumFractionDigits: 1 })} ${unit}` : '—') },
    { key: 'count', header: t('mg.count'), numeric: true, cell: (r) => r.measurements },
  ]

  return (
    <div className="flex flex-col gap-4">
      <PageHeader eyebrow={t('eyebrow.monitor')} title={t('mg.title')} subtitle={t('mg.subtitle')}>
        <MethodBadge method="statistical" />
      </PageHeader>
      <FilterBar>
        <FilterSelect id="mg-metric" label={t('mg.measure')} value={metric} onChange={(v) => setMetric(v as GrowthMetric)}>
          {METRICS.map((m) => <option key={m} value={m}>{t(`mg.metric.${m}` as TKey)}</option>)}
        </FilterSelect>
        <Segmented label={t('hv.period')} value={String(months)} onChange={(v) => setMonths(Number(v))} options={SPANS.map((m) => ({ value: String(m), label: t('hv.months', { count: m }) }))} />
      </FilterBar>
      {q.isLoading && <LoadingBlock label={t('mg.loading')} />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {d && d.measured_assets === 0 && <EmptyState icon="growth" title={t('mg.none')}>{t('mg.noneBody')}</EmptyState>}
      {d && d.measured_assets > 0 && (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <StatTile label={t('mg.medianTile')} value={d.median_change_pct != null ? `${fmt.number(d.median_change_pct, { maximumFractionDigits: 1 })}%` : '—'} note={t('mg.medianNote', { count: d.comparable_assets })} />
            <StatTile label={t('mg.measuredTile')} value={fmt.number(d.measured_assets)} />
            <StatTile label={t('mg.comparableTile')} value={fmt.number(d.comparable_assets)} note={t('mg.comparableNote', { days: d.min_span_days })} />
          </div>
          <p className="text-sm">
            {d.median_change_pct != null
              ? t('mg.summary', { median: fmt.number(d.median_change_pct, { maximumFractionDigits: 1 }), count: d.comparable_assets, measured: d.measured_assets })
              : t('mg.summaryNone', { measured: d.measured_assets, days: d.min_span_days })}
          </p>
          <LedgerTable caption={t('mg.title')} columns={columns} rows={d.assets} rowKey={(r) => r.asset_id} />
        </>
      )}
      <p className="text-[13px] text-ink-2">{t('mg.note', { days: d?.min_span_days ?? 30 })}</p>
    </div>
  )
}
