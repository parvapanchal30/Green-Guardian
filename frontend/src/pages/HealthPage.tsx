import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { MethodBadge, PageHeader } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock } from '../components/states'
import { useI18n } from '../i18n'
import { useHealthMonitor } from '../lib/monitor'

const SPANS = [4, 12, 26, 52] as const

/**
 * Health over time, from recorded health scores only: today's bands, each week's scores (how many, their mean and
 * their bands), the assets whose score fell most, and living assets nobody has looked at recently.
 */
export function HealthPage() {
  const { ws } = useWorkspaceCtx()
  const { t, te, fmt } = useI18n()
  const [weeks, setWeeks] = useState<number>(12)
  const q = useHealthMonitor(ws, weeks)
  const d = q.data
  const living = d ? d.now.healthy + d.now.at_risk + d.now.critical + d.now.no_data : 0
  const busiest = Math.max(1, ...(d?.weekly.map((w) => w.observations) ?? [1]))

  return (
    <div className="space-y-6">
      <PageHeader title={t('mh.title')} subtitle={t('mh.subtitle')}><MethodBadge method="statistical" /></PageHeader>
      <div role="group" aria-label={t('mh.span')} className="inline-flex overflow-hidden rounded border border-line text-sm">
        {SPANS.map((w) => (
          <button key={w} type="button" aria-pressed={weeks === w} onClick={() => setWeeks(w)} className={`px-3 py-1.5 ${weeks === w ? 'bg-surface-2 font-medium' : 'hover:bg-surface-2'}`}>
            {t('mh.weeks', { count: w })}
          </button>
        ))}
      </div>
      {q.isLoading && <LoadingBlock label={t('mh.loading')} />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {d && living === 0 && <EmptyState title={t('mh.none')}>{t('mh.noneBody')}</EmptyState>}
      {d && living > 0 && (
        <>
          <section aria-labelledby="mh-now" className="grid gap-3 sm:grid-cols-4">
            <h2 id="mh-now" className="sr-only">{t('mh.now')}</h2>
            {(['healthy', 'at_risk', 'critical'] as const).map((b) => (
              <div key={b} className="rounded-lg border border-line bg-surface p-3">
                <p className="text-xs text-ink-3">{te('health', b)}</p>
                <p className="text-2xl font-semibold">{d.now[b]}</p>
              </div>
            ))}
            <div className="rounded-lg border border-line bg-surface p-3">
              <p className="text-xs text-ink-3">{te('health', 'none')}</p>
              <p className="text-2xl font-semibold">{d.now.no_data}</p>
            </div>
          </section>

          <section aria-labelledby="mh-weeks">
            <h2 id="mh-weeks" className="mb-2 font-semibold">{t('mh.weekly')}</h2>
            <ul aria-label={t('mh.weekly')} className="space-y-1 text-sm">
              {d.weekly.map((w) => (
                <li key={w.week_start} className="grid grid-cols-[6rem_1fr_9rem] items-center gap-2">
                  <span className="text-ink-2">{fmt.date(w.week_start)}</span>
                  <span className="flex h-3 overflow-hidden rounded bg-surface-2" aria-hidden="true" style={{ width: `${(w.observations / busiest) * 100}%`, minWidth: w.observations ? '0.5rem' : 0 }}>
                    <span className="bg-healthy" style={{ flex: w.healthy }} />
                    <span className="bg-at-risk" style={{ flex: w.at_risk }} />
                    <span className="bg-critical" style={{ flex: w.critical }} />
                  </span>
                  <span className="text-xs">
                    {w.observations ? t('mh.weekLine', { count: w.observations, mean: fmt.number(w.mean_score ?? 0, { maximumFractionDigits: 1 }) }) : <span className="text-ink-3">{t('mh.noScores')}</span>}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-1 text-xs text-ink-3">{t('mh.chartNote')}</p>
          </section>

          <div className="grid gap-6 lg:grid-cols-2">
            <section aria-labelledby="mh-decl">
              <h2 id="mh-decl" className="mb-2 font-semibold">{t('mh.declining')}</h2>
              {d.declining.length === 0 ? <p className="text-sm text-ink-3">{t('mh.noDecline')}</p> : (
                <ul className="space-y-1 text-sm">
                  {d.declining.map((c) => (
                    <li key={c.asset_id} className="flex flex-wrap items-baseline gap-x-2">
                      <Link className="text-moss hover:underline" to={`/w/${ws}/assets/${c.asset_id}`}>{c.label}</Link>
                      <span>{fmt.number(c.first_score)} → {fmt.number(c.latest_score)}</span>
                      <span className="font-medium text-critical">{fmt.number(c.change, { maximumFractionDigits: 1 })}</span>
                      <span className="text-xs text-ink-3">{fmt.date(c.first_at)} – {fmt.date(c.latest_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section aria-labelledby="mh-unobs">
              <h2 id="mh-unobs" className="mb-2 font-semibold">{t('mh.notObserved', { days: d.not_observed_days, count: d.not_observed_count })}</h2>
              {d.not_observed.length === 0 ? <p className="text-sm text-ink-3">{t('mh.allObserved')}</p> : (
                <ul className="space-y-1 text-sm">
                  {d.not_observed.map((u) => (
                    <li key={u.asset_id} className="flex flex-wrap items-baseline gap-x-2">
                      <Link className="text-moss hover:underline" to={`/w/${ws}/assets/${u.asset_id}`}>{u.label}</Link>
                      <span className="text-xs text-ink-3">{u.last_observed_at ? t('mh.lastSeen', { when: fmt.relative(u.last_observed_at) }) : t('mh.never')}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </>
      )}
      <p className="text-xs text-ink-3">{t('mh.note')}</p>
    </div>
  )
}
