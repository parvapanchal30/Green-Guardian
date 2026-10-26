import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { MethodBadge, PageHeader } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock } from '../components/states'
import { Card, HealthBar, SectionHeading, Segmented } from '../components/ui'
import { useI18n } from '../i18n'
import { useHealthMonitor, type HealthWeek } from '../lib/monitor'

const SPANS = [4, 12, 26, 52] as const

/**
 * Health over time (ADR-076), from recorded health scores only: each week's scores drawn by band with their mean,
 * today's bands, the plants whose score fell most, and living plants nobody has looked at recently.
 */
export function HealthPage() {
  const { ws } = useWorkspaceCtx()
  const { t, fmt } = useI18n()
  const [weeks, setWeeks] = useState<number>(12)
  const q = useHealthMonitor(ws, weeks)
  const d = q.data
  const living = d ? d.now.healthy + d.now.at_risk + d.now.critical + d.now.no_data : 0

  return (
    <div className="flex flex-col gap-4">
      <PageHeader eyebrow={t('eyebrow.monitor')} title={t('mh.title')} subtitle={t('mh.subtitle')}>
        <MethodBadge method="statistical" />
        <Segmented label={t('mh.span')} value={String(weeks)} onChange={(v) => setWeeks(Number(v))} options={SPANS.map((w) => ({ value: String(w), label: t('mh.weeks', { count: w }) }))} />
      </PageHeader>
      {q.isLoading && <LoadingBlock label={t('mh.loading')} />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {d && living === 0 && <EmptyState icon="health" title={t('mh.none')}>{t('mh.noneBody')}</EmptyState>}
      {d && living > 0 && (
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.75fr)_minmax(0,1fr)]">
          <Card className="p-4">
            <section aria-labelledby="mh-weeks">
              <SectionHeading id="mh-weeks" title={t('mh.weekly')}>
                <span className="text-[13px] text-ink-2">{t('mh.chartKey')}</span>
              </SectionHeading>
              <WeeklyChart weekly={d.weekly} />
              <div className="mt-2 flex flex-wrap gap-4 text-[13px]">
                <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 bg-healthy" />{t('mh.band.healthy')}</span>
                <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 bg-at-risk" />{t('mh.band.at_risk')}</span>
                <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 bg-critical" />{t('mh.band.critical')}</span>
              </div>
              <details className="mt-3 text-sm">
                <summary className="cursor-pointer text-ink-2">{t('mh.asList')}</summary>
                <ul aria-label={t('mh.weekly')} className="mt-2 flex flex-col gap-1">
                  {d.weekly.map((w) => (
                    <li key={w.week_start} className="grid grid-cols-[7rem_1fr] gap-2">
                      <span className="font-mono text-xs text-ink-2">{fmt.date(w.week_start)}</span>
                      <span>
                        {w.observations ? t('mh.weekLine', { count: w.observations, mean: fmt.number(w.mean_score ?? 0, { maximumFractionDigits: 1 }) }) : <span className="text-ink-3">{t('mh.noScores')}</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              </details>
            </section>
          </Card>

          <div className="flex flex-col gap-3.5">
            <Card className="p-4">
              <section aria-labelledby="mh-now">
                <SectionHeading id="mh-now" title={t('mh.now')} />
                <HealthBar healthy={d.now.healthy} atRisk={d.now.at_risk} critical={d.now.critical} noData={d.now.no_data} />
              </section>
            </Card>
            <Card className="p-4">
              <section aria-labelledby="mh-decl">
                <SectionHeading id="mh-decl" title={t('mh.declining')} />
                {d.declining.length === 0 ? <p className="text-sm text-ink-2">{t('mh.noDecline')}</p> : (
                  <ul className="flex flex-col text-sm">
                    {d.declining.map((c) => (
                      <li key={c.asset_id} className="flex items-baseline gap-2.5 border-b border-line-soft py-2 last:border-0">
                        <Link className="flex-1 text-moss hover:underline" to={`/w/${ws}/assets/${c.asset_id}`}>{c.label}</Link>
                        <span className="font-mono text-[13px]">{fmt.number(c.first_score)} → {fmt.number(c.latest_score)}</span>
                        <b className={`w-12 text-right font-mono text-[13px] ${c.change <= -20 ? 'text-critical' : 'text-at-risk'}`}>{fmt.number(c.change, { maximumFractionDigits: 1 })}</b>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </Card>
            <Card className="p-4">
              <section aria-labelledby="mh-unobs">
                <SectionHeading id="mh-unobs" title={t('mh.notObserved', { days: d.not_observed_days, count: d.not_observed_count })} />
                {d.not_observed.length === 0 ? <p className="text-sm text-ink-2">{t('mh.allObserved')}</p> : (
                  <ul className="flex flex-col text-sm">
                    {d.not_observed.map((u) => (
                      <li key={u.asset_id} className="flex items-baseline gap-2.5 border-b border-line-soft py-2 last:border-0">
                        <Link className="flex-1 text-moss hover:underline" to={`/w/${ws}/assets/${u.asset_id}`}>{u.label}</Link>
                        <span className="text-[13px] text-at-risk">{u.last_observed_at ? t('mh.lastSeen', { when: fmt.relative(u.last_observed_at) }) : t('mh.never')}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {d.not_observed.length > 0 && <Link to={`/w/${ws}/inspections`} className="mt-2 inline-block text-sm text-moss underline">{t('mh.planInspection')}</Link>}
              </section>
            </Card>
          </div>
        </div>
      )}
      <p className="text-[13px] text-ink-2">{t('mh.note')}</p>
    </div>
  )
}

/** Scores recorded each week, stacked by band, with the week's mean above the bar. Empty weeks stay empty. */
function WeeklyChart({ weekly }: { weekly: HealthWeek[] }) {
  const { t, fmt } = useI18n()
  const W = 620
  const H = 244
  const L = 34
  const TOP = 24
  const BOTTOM = 196
  const most = Math.max(1, ...weekly.map((w) => w.observations))
  const slot = (W - L - 6) / Math.max(1, weekly.length)
  const bar = Math.min(34, slot * 0.7)
  const y = (n: number) => BOTTOM - ((BOTTOM - TOP) * n) / most
  const every = Math.max(1, Math.ceil(weekly.length / 6))
  const scored = weekly.filter((w) => w.observations > 0)
  const label = t('mh.chartLabel', { weeks: weekly.length, scored: scored.length, critical: weekly.reduce((a, w) => a + w.critical, 0), atRisk: weekly.reduce((a, w) => a + w.at_risk, 0) })
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={label}>
      {[0, most / 2, most].map((v, k) => (
        <g key={k}>
          <line x1={L} x2={W - 4} y1={y(v)} y2={y(v)} stroke={k === 0 ? 'var(--color-line)' : 'var(--color-line-soft)'} />
          <text x={L - 6} y={y(v) + 4} textAnchor="end" fontSize="10" fontFamily="var(--font-mono)" fill="var(--color-ink-2)">{fmt.number(v, { maximumFractionDigits: 1 })}</text>
        </g>
      ))}
      {weekly.map((w, i) => {
        const x = L + slot * i + (slot - bar) / 2
        let base = BOTTOM
        const seg = (n: number, color: string) => {
          if (n <= 0) return null
          const h = BOTTOM - y(n)
          base -= h
          return <rect x={x} y={base} width={bar} height={Math.max(0, h - 1)} fill={color} />
        }
        return (
          <g key={w.week_start}>
            <title>{w.observations ? `${fmt.date(w.week_start)} · ${t('mh.weekLine', { count: w.observations, mean: fmt.number(w.mean_score ?? 0, { maximumFractionDigits: 1 }) })}` : `${fmt.date(w.week_start)} · ${t('mh.noScores')}`}</title>
            {seg(w.healthy, 'var(--color-healthy)')}
            {seg(w.at_risk, 'var(--color-at-risk)')}
            {seg(w.critical, 'var(--color-critical)')}
            {w.mean_score !== null && w.observations > 0 && (
              <text x={x + bar / 2} y={y(w.observations) - 6} textAnchor="middle" fontSize="10" fontFamily="var(--font-mono)" fontWeight={w.critical ? 600 : 400} fill={w.critical ? 'var(--color-critical)' : 'var(--color-ink-2)'}>
                {fmt.number(w.mean_score, { maximumFractionDigits: 1 })}
              </text>
            )}
            {i % every === 0 && (
              <text x={x + bar / 2} y={BOTTOM + 16} textAnchor="middle" fontSize="10" fontFamily="var(--font-mono)" fill="var(--color-ink-2)">{fmt.date(w.week_start).replace(/,? \d{4}$/, '')}</text>
            )}
          </g>
        )
      })}
      <text x={L} y={H - 4} fontSize="11" fill="var(--color-ink-2)">{t('mh.chartFoot')}</text>
    </svg>
  )
}
