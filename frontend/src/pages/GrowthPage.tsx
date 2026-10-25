import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { MethodBadge, PageHeader, input } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock } from '../components/states'
import { useI18n, type TKey } from '../i18n'
import { UNIT, useAssetGrowth, useGrowthMonitor, type GrowthMetric, type Measurement } from '../lib/monitor'

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
      <h2 id="growth" className="mb-2 font-semibold">{t('mg.panelTitle')}</h2>
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

/** Growth between recorded measurements, per asset, over a period. */
export function GrowthPage() {
  const { ws } = useWorkspaceCtx()
  const { t, fmt } = useI18n()
  const [metric, setMetric] = useState<GrowthMetric>('height_cm')
  const [months, setMonths] = useState<number>(12)
  const q = useGrowthMonitor(ws, metric, months)
  const d = q.data
  const unit = UNIT[metric]

  return (
    <div className="space-y-6">
      <PageHeader title={t('mg.title')} subtitle={t('mg.subtitle')}><MethodBadge method="statistical" /></PageHeader>
      <div className="flex flex-wrap items-center gap-2">
        <label className="sr-only" htmlFor="mg-metric">{t('mg.measure')}</label>
        <select id="mg-metric" value={metric} onChange={(e) => setMetric(e.target.value as GrowthMetric)} className={`${input} max-w-[12rem]`}>
          {METRICS.map((m) => <option key={m} value={m}>{t(`mg.metric.${m}` as TKey)}</option>)}
        </select>
        <div role="group" aria-label={t('hv.period')} className="inline-flex overflow-hidden rounded border border-line text-sm">
          {SPANS.map((m) => (
            <button key={m} type="button" aria-pressed={months === m} onClick={() => setMonths(m)} className={`px-3 py-1.5 ${months === m ? 'bg-surface-2 font-medium' : 'hover:bg-surface-2'}`}>
              {t('hv.months', { count: m })}
            </button>
          ))}
        </div>
      </div>
      {q.isLoading && <LoadingBlock label={t('mg.loading')} />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {d && d.measured_assets === 0 && <EmptyState title={t('mg.none')}>{t('mg.noneBody')}</EmptyState>}
      {d && d.measured_assets > 0 && (
        <>
          <p className="text-sm">
            {d.median_change_pct != null
              ? t('mg.summary', { median: fmt.number(d.median_change_pct, { maximumFractionDigits: 1 }), count: d.comparable_assets, measured: d.measured_assets })
              : t('mg.summaryNone', { measured: d.measured_assets, days: d.min_span_days })}
          </p>
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">{t('mg.title')}</caption>
              <thead className="border-b border-line text-ink-2">
                <tr>
                  <th className="p-2 font-medium">{t('mg.asset')}</th>
                  <th className="p-2 font-medium">{t('mg.first')}</th>
                  <th className="p-2 font-medium">{t('mg.latest')}</th>
                  <th className="p-2 font-medium">{t('mg.change')}</th>
                  <th className="p-2 font-medium">{t('mg.perYear')}</th>
                  <th className="p-2 font-medium">{t('mg.count')}</th>
                </tr>
              </thead>
              <tbody>
                {d.assets.map((r) => (
                  <tr key={r.asset_id} className="border-b border-line last:border-0">
                    <td className="p-2"><Link className="text-moss hover:underline" to={`/w/${ws}/assets/${r.asset_id}`}>{r.label}</Link></td>
                    <td className="p-2">{fmt.number(r.first)} {unit} <span className="text-xs text-ink-3">{fmt.date(r.first_at)}</span></td>
                    <td className="p-2">{fmt.number(r.latest)} {unit} <span className="text-xs text-ink-3">{fmt.date(r.latest_at)}</span></td>
                    <td className="p-2">{r.change != null ? `${r.change > 0 ? '+' : ''}${fmt.number(r.change)} ${unit} (${fmt.number(r.change_pct ?? 0, { maximumFractionDigits: 1 })}%)` : <span className="text-ink-3">{t('mg.notYet')}</span>}</td>
                    <td className="p-2">{r.per_year != null ? `${fmt.number(r.per_year, { maximumFractionDigits: 1 })} ${unit}` : '—'}</td>
                    <td className="p-2">{r.measurements}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <p className="text-xs text-ink-3">{t('mg.note', { days: d?.min_span_days ?? 30 })}</p>
    </div>
  )
}
