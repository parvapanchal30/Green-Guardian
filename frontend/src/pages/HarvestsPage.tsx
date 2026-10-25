import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { PageHeader, btn, input } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock } from '../components/states'
import { StatusChip } from '../components/StatusChip'
import { useI18n } from '../i18n'
import { downloadCsv, toCsv } from '../lib/csv'
import { useHarvestOverview } from '../lib/harvests'

const PERIODS = [3, 6, 12, 36] as const // months

function since(months: number, now = new Date()): string {
  const d = new Date(now)
  d.setMonth(d.getMonth() - months)
  return d.toISOString()
}

/**
 * Every recorded harvest of the workspace in a period: totals per unit (only kg and t are added, as weight), a monthly
 * chart of that weight, totals per crop, and the records themselves. Corrections are applied; withdrawn records left out.
 */
export function HarvestsPage() {
  const { ws } = useWorkspaceCtx()
  const { t, te, fmt } = useI18n()
  const [months, setMonths] = useState<number>(12)
  const [assetId, setAssetId] = useState('')
  const [from] = useState(() => Object.fromEntries(PERIODS.map((m) => [m, since(m)])) as Record<number, string>)
  const q = useHarvestOverview(ws, { since: from[months], asset_id: assetId || undefined })
  const amounts = (by: Record<string, number>) => Object.entries(by).map(([u, n]) => `${fmt.number(n, { maximumFractionDigits: 3 })} ${te('unit', u)}`).join(' · ')
  const data = q.data
  const peak = Math.max(0, ...(data?.by_month.map((m) => m.mass_tonnes) ?? [0]))

  function exportCsv() {
    if (!data) return
    const rows = data.records.map((r) => [r.harvested_at.slice(0, 10), r.asset_label, r.quantity, r.unit, r.grade, r.note])
    downloadCsv(`harvests-${data.since.slice(0, 10)}-to-${data.until.slice(0, 10)}.csv`, toCsv(['date', 'asset', 'quantity', 'unit', 'grade', 'note'], rows))
  }

  return (
    <div className="space-y-6">
      <PageHeader title={t('hv.title')} subtitle={t('hv.subtitle')}>
        {data && data.records.length > 0 && <button type="button" className={btn} onClick={exportCsv}>{t('hv.export')}</button>}
      </PageHeader>
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label={t('hv.period')} className="inline-flex overflow-hidden rounded border border-line text-sm">
          {PERIODS.map((m) => (
            <button key={m} type="button" aria-pressed={months === m} onClick={() => setMonths(m)} className={`px-3 py-1.5 ${months === m ? 'bg-surface-2 font-medium' : 'hover:bg-surface-2'}`}>
              {t('hv.months', { count: m })}
            </button>
          ))}
        </div>
        {data && (data.by_asset.length > 1 || assetId) && (
          <>
            <label className="sr-only" htmlFor="hv-asset">{t('hv.crop')}</label>
            <select id="hv-asset" value={assetId} onChange={(e) => setAssetId(e.target.value)} className={`${input} max-w-[14rem]`}>
              <option value="">{t('hv.allCrops')}</option>
              {data.by_asset.map((a) => <option key={a.asset_id} value={a.asset_id}>{a.asset_label}</option>)}
            </select>
          </>
        )}
      </div>

      {q.isLoading && <LoadingBlock label={t('hv.loading')} />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {data && data.totals.records === 0 && <EmptyState title={t('hv.none')}>{t('hv.noneBody')}</EmptyState>}

      {data && data.totals.records > 0 && (
        <>
          <section aria-labelledby="hv-totals" className="grid gap-3 sm:grid-cols-3">
            <h2 id="hv-totals" className="sr-only">{t('hv.totals')}</h2>
            <div className="rounded-lg border border-line bg-surface p-3">
              <p className="text-xs text-ink-3">{t('hv.weight')}</p>
              <p className="text-2xl font-semibold">{fmt.number(data.totals.mass_tonnes, { maximumFractionDigits: 3 })} t</p>
            </div>
            <div className="rounded-lg border border-line bg-surface p-3">
              <p className="text-xs text-ink-3">{t('hv.byUnit')}</p>
              <p className="text-sm">{amounts(data.totals.by_unit)}</p>
            </div>
            <div className="rounded-lg border border-line bg-surface p-3">
              <p className="text-xs text-ink-3">{t('hv.records')}</p>
              <p className="text-2xl font-semibold">{fmt.number(data.totals.records)}</p>
            </div>
          </section>

          <section aria-labelledby="hv-months">
            <h2 id="hv-months" className="mb-2 font-semibold">{t('hv.perMonth')}</h2>
            <ul className="space-y-1 text-sm" aria-label={t('hv.perMonth')}>
              {data.by_month.map((m) => (
                <li key={m.month} className="grid grid-cols-[5rem_1fr_auto] items-center gap-2">
                  <span className="text-ink-2">{fmt.month(`${m.month}-15T00:00:00Z`)}</span>
                  <span className="h-3 rounded bg-surface-2" aria-hidden="true">
                    <span className="block h-3 rounded bg-moss" style={{ width: `${peak > 0 ? Math.max(2, (m.mass_tonnes / peak) * 100) : 0}%` }} />
                  </span>
                  <span className="text-xs">{m.mass_tonnes > 0 ? `${fmt.number(m.mass_tonnes, { maximumFractionDigits: 3 })} t` : ''} {amounts(Object.fromEntries(Object.entries(m.by_unit).filter(([u]) => u !== 'kg' && u !== 't')))}</span>
                </li>
              ))}
            </ul>
            <p className="mt-1 text-xs text-ink-3">{t('hv.chartNote')}</p>
          </section>

          <section aria-labelledby="hv-assets">
            <h2 id="hv-assets" className="mb-2 font-semibold">{t('hv.perCrop')}</h2>
            <div className="overflow-x-auto rounded-lg border border-line bg-surface">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">{t('hv.perCrop')}</caption>
                <thead className="border-b border-line text-ink-2"><tr><th className="p-2 font-medium">{t('hv.crop')}</th><th className="p-2 font-medium">{t('hv.weight')}</th><th className="p-2 font-medium">{t('hv.byUnit')}</th><th className="p-2 font-medium">{t('hv.records')}</th></tr></thead>
                <tbody>
                  {data.by_asset.map((a) => (
                    <tr key={a.asset_id} className="border-b border-line last:border-0">
                      <td className="p-2"><Link className="text-moss hover:underline" to={`/w/${ws}/assets/${a.asset_id}`}>{a.asset_label}</Link></td>
                      <td className="p-2">{a.mass_tonnes > 0 ? `${fmt.number(a.mass_tonnes, { maximumFractionDigits: 3 })} t` : '—'}</td>
                      <td className="p-2">{amounts(a.by_unit)}</td>
                      <td className="p-2">{a.records}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section aria-labelledby="hv-records">
            <h2 id="hv-records" className="mb-2 font-semibold">{t('hv.recordsTitle')}</h2>
            <ul className="space-y-1 text-sm">
              {data.records.map((r) => (
                <li key={r.id} className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-xs text-ink-3">{fmt.date(r.harvested_at)}</span>
                  <Link className="text-moss hover:underline" to={`/w/${ws}/assets/${r.asset_id}`}>{r.asset_label}</Link>
                  <span className="font-medium">{fmt.number(r.quantity, { maximumFractionDigits: 3 })} {te('unit', r.unit)}</span>
                  {r.grade && <span>{t('harvest.grade', { grade: r.grade })}</span>}
                  {r.supersedes_id && <StatusChip tone="at-risk">{t('harvest.correctionChip')}</StatusChip>}
                  {r.note && <span className="text-ink-2">{r.note}</span>}
                </li>
              ))}
            </ul>
            {data.truncated && <p className="mt-1 text-xs text-ink-3">{t('hv.truncated')}</p>}
          </section>
        </>
      )}
      <p className="text-xs text-ink-3">{t('hv.note')}</p>
    </div>
  )
}
