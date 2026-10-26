import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { Counts, ReportFrame, Stat, type Figure } from '../components/ReportFrame'
import { ErrorState, LoadingBlock } from '../components/states'
import { useI18n } from '../i18n'
import { useAnalytics, useImpact, usePeriod, type AnalyticsReport, type ImpactReport } from '../lib/reports'
import { analyticsSentence, impactSentence } from '../lib/summary'

function sorted(rec: Record<string, number>): [string, number][] {
  return Object.entries(rec).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
}

function AnalyticsBody({ q }: { q: ReturnType<typeof useAnalytics> }) {
  const { t, te, fmt } = useI18n()
  if (q.isLoading) return <LoadingBlock label={t('rep.loading')} />
  if (q.error || !q.data) return <ErrorState error={q.error ?? new Error(t('rep.loading'))} onRetry={() => q.refetch()} />
  const r = q.data
  const named = (group: string, rec: Record<string, number>): [string, number][] => sorted(rec).map(([k, n]) => [te(group, k), n])
  const pct = (v: number | null) => (v == null ? '—' : `${fmt.number(v, { maximumFractionDigits: 1 })}%`)
  return (
    <div className="grid items-start gap-4 lg:grid-cols-2">
      <section aria-labelledby="ra-issues" className="space-y-3 rounded-lg border border-line bg-surface p-4 break-inside-avoid">
        <h2 id="ra-issues" className="text-[19px] font-semibold">{t('rep.issues')}</h2>
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <Stat label={t('rep.opened')} value={r.issues.opened} />
          <Stat label={t('rep.closed')} value={r.issues.closed} />
          <Stat label={t('rep.stillOpen')} value={r.issues.still_open} />
          <Stat label={t('rep.medianClose')} value={r.issues.median_days_to_close == null ? '—' : t('rep.days', { n: fmt.number(r.issues.median_days_to_close, { maximumFractionDigits: 1 }) })} />
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <div><h3 className="mb-1 font-mono text-[11px] tracking-wide text-ink-2 uppercase">{t('rep.byCategory')}</h3><Counts label={t('rep.byCategory')} items={named('issueCategory', r.issues.opened_by_category)} /></div>
          <div><h3 className="mb-1 font-mono text-[11px] tracking-wide text-ink-2 uppercase">{t('rep.bySeverity')}</h3><Counts label={t('rep.bySeverity')} items={named('severity', r.issues.opened_by_severity)} /></div>
          <div><h3 className="mb-1 font-mono text-[11px] tracking-wide text-ink-2 uppercase">{t('rep.byOutcome')}</h3><Counts label={t('rep.byOutcome')} items={named('outcome', r.issues.closed_by_outcome)} /></div>
        </div>
      </section>
      <section aria-labelledby="ra-tasks" className="space-y-3 rounded-lg border border-line bg-surface p-4 break-inside-avoid">
        <h2 id="ra-tasks" className="text-[19px] font-semibold">{t('rep.tasks')}</h2>
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <Stat label={t('rep.created')} value={r.tasks.created} />
          <Stat label={t('rep.completed')} value={r.tasks.completed} />
          <Stat label={t('rep.onTime')} value={pct(r.tasks.on_time_pct)} note={r.tasks.completed_with_due_date ? t('rep.onTimeNote', { done: r.tasks.completed_on_time, of: r.tasks.completed_with_due_date }) : undefined} />
          <Stat label={t('rep.overdueNow')} value={r.tasks.overdue_now} />
        </div>
        <div className="max-w-xs"><h3 className="mb-1 font-mono text-[11px] tracking-wide text-ink-2 uppercase">{t('rep.completedByType')}</h3><Counts label={t('rep.completedByType')} items={named('taskType', r.tasks.completed_by_type)} /></div>
      </section>
      <section aria-labelledby="ra-work" className="grid gap-4 rounded-lg border border-line bg-surface p-4 break-inside-avoid sm:grid-cols-2">
        <div>
          <h2 id="ra-work" className="mb-2 text-[19px] font-semibold">{t('rep.work', { n: r.actions.recorded })}</h2>
          <Counts label={t('rep.work', { n: r.actions.recorded })} items={named('actionKind', r.actions.by_kind)} />
        </div>
        <div>
          <h3 className="mb-2 text-[19px] font-semibold">{t('rep.products')}</h3>
          <Counts label={t('rep.products')} items={r.actions.top_products.map((p) => [p.name, p.count])} />
        </div>
      </section>
      <section aria-labelledby="ra-obs" className="space-y-3 rounded-lg border border-line bg-surface p-4 break-inside-avoid">
        <h2 id="ra-obs" className="text-[19px] font-semibold">{t('rep.observations')}</h2>
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <Stat label={t('rep.recorded')} value={r.observations.recorded} />
          <Stat label={t('rep.withScore')} value={r.observations.with_health_score} />
          <Stat label={t('rep.withMeasure')} value={r.observations.with_measurements} />
          <Stat label={t('rep.assetsObserved')} value={r.observations.assets_observed} note={t('rep.observers', { count: r.observations.observers })} />
        </div>
      </section>
      <section aria-labelledby="ra-agent" className="space-y-3 lg:col-span-2 rounded-lg border border-line bg-surface p-4 break-inside-avoid">
        <h2 id="ra-agent" className="text-[19px] font-semibold">{t('rep.agent')}</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <Stat label={t('rep.suggested')} value={r.agent.suggested} />
          <Stat label={te('rec.status', 'accepted')} value={r.agent.accepted} />
          <Stat label={te('rec.status', 'dismissed')} value={r.agent.dismissed} />
          <Stat label={te('rec.status', 'expired')} value={r.agent.expired} />
          <Stat label={t('rep.openNow')} value={r.agent.open_now} />
        </div>
      </section>
    </div>
  )
}

function analyticsFigures(r: AnalyticsReport, t: ReturnType<typeof useI18n>['t']): Figure[] {
  const s = (section: string, label: string, value: number | string | null, note?: string): Figure => ({ section, label, value, note })
  return [
    s(t('rep.issues'), t('rep.opened'), r.issues.opened),
    s(t('rep.issues'), t('rep.closed'), r.issues.closed),
    s(t('rep.issues'), t('rep.stillOpen'), r.issues.still_open),
    s(t('rep.issues'), t('rep.medianClose'), r.issues.median_days_to_close),
    ...Object.entries(r.issues.opened_by_category).map(([k, n]) => s(t('rep.byCategory'), k, n)),
    ...Object.entries(r.issues.opened_by_severity).map(([k, n]) => s(t('rep.bySeverity'), k, n)),
    ...Object.entries(r.issues.closed_by_outcome).map(([k, n]) => s(t('rep.byOutcome'), k, n)),
    s(t('rep.tasks'), t('rep.created'), r.tasks.created),
    s(t('rep.tasks'), t('rep.completed'), r.tasks.completed),
    s(t('rep.tasks'), t('rep.onTime'), r.tasks.on_time_pct, `${r.tasks.completed_on_time}/${r.tasks.completed_with_due_date}`),
    s(t('rep.tasks'), t('rep.overdueNow'), r.tasks.overdue_now),
    ...Object.entries(r.actions.by_kind).map(([k, n]) => s(t('rep.work', { n: r.actions.recorded }), k, n)),
    ...r.actions.top_products.map((p) => s(t('rep.products'), p.name, p.count)),
    s(t('rep.observations'), t('rep.recorded'), r.observations.recorded),
    s(t('rep.observations'), t('rep.withScore'), r.observations.with_health_score),
    s(t('rep.observations'), t('rep.withMeasure'), r.observations.with_measurements),
    s(t('rep.observations'), t('rep.assetsObserved'), r.observations.assets_observed),
    s(t('rep.agent'), t('rep.suggested'), r.agent.suggested),
    s(t('rep.agent'), 'accepted', r.agent.accepted),
    s(t('rep.agent'), 'dismissed', r.agent.dismissed),
    s(t('rep.agent'), 'expired', r.agent.expired),
  ]
}

/** Analytics: what happened in the period, counted from records. */
export function AnalyticsPage() {
  const { ws } = useWorkspaceCtx()
  const { t, fmt } = useI18n()
  const period = usePeriod()
  const q = useAnalytics(ws, period.since)
  return (
    <ReportFrame title={t('rep.analyticsTitle')} subtitle={t('rep.analyticsSubtitle')} slug="analytics" period={period} figures={q.data ? analyticsFigures(q.data, t) : null} summary={q.data ? analyticsSentence(q.data, t, fmt.number) : null}>
      <AnalyticsBody q={q} />
    </ReportFrame>
  )
}

function ImpactBody({ q }: { q: ReturnType<typeof useImpact> }) {
  const { t, fmt } = useI18n()
  if (q.isLoading) return <LoadingBlock label={t('rep.loading')} />
  if (q.error || !q.data) return <ErrorState error={q.error ?? new Error(t('rep.loading'))} onRetry={() => q.refetch()} />
  const r = q.data
  const pct = (v: number | null) => (v == null ? '—' : `${fmt.number(v, { maximumFractionDigits: 1 })}%`)
  return (
    <div className="grid items-start gap-4 lg:grid-cols-2">
      <section aria-labelledby="ri-plant" className="space-y-3 rounded-lg border border-line bg-surface p-4 break-inside-avoid">
        <h2 id="ri-plant" className="text-[19px] font-semibold">{t('rep.planting')}</h2>
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <Stat label={t('rep.registered')} value={r.planting.registered} />
          <Stat label={t('rep.planted')} value={r.planting.planted} note={t('rep.plantedNote')} />
          <Stat label={t('rep.batches')} value={r.planting.batches_registered} />
          <Stat label={t('rep.plantsInBatches')} value={fmt.number(r.planting.plants_in_batches)} />
        </div>
        <div className="max-w-xs"><h3 className="mb-1 font-mono text-[11px] tracking-wide text-ink-2 uppercase">{t('rep.bySpecies')}</h3><Counts label={t('rep.bySpecies')} items={r.planting.by_species.map((s) => [s.name, s.count])} /></div>
      </section>
      <section aria-labelledby="ri-surv" className="space-y-3 rounded-lg border border-line bg-surface p-4 break-inside-avoid">
        <h2 id="ri-surv" className="text-[19px] font-semibold">{t('rep.survival')}</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat label={t('rep.survivalRate')} value={pct(r.survival.rate)} note={t('rep.survivalNote', { alive: r.survival.alive, dead: r.survival.dead })} />
        </div>
        {r.survival.by_species.length > 0 && (
          <div className="relative overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">{t('rep.survival')}</caption>
              <thead className="border-b border-line text-ink-2"><tr><th className="p-2 font-medium">{t('rep.species')}</th><th className="p-2 font-medium">{t('rep.alive')}</th><th className="p-2 font-medium">{t('rep.dead')}</th><th className="p-2 font-medium">{t('rep.survivalRate')}</th></tr></thead>
              <tbody>{r.survival.by_species.map((s) => <tr key={s.species} className="border-b border-line last:border-0"><td className="p-2">{s.species}</td><td className="p-2">{s.alive}</td><td className="p-2">{s.dead}</td><td className="p-2">{pct(s.rate)}</td></tr>)}</tbody>
            </table>
          </div>
        )}
      </section>
      <section aria-labelledby="ri-other" className="grid gap-3 sm:grid-cols-2 lg:col-span-2 lg:grid-cols-4">
        <h2 id="ri-other" className="sr-only">{t('rep.healthGrowth')}</h2>
        <Stat label={t('rep.healthyShare')} value={r.health.assets_compared ? `${pct(r.health.healthy_share_start)} → ${pct(r.health.healthy_share_end)}` : '—'} note={r.health.assets_compared ? t('rep.healthNote', { count: r.health.assets_compared }) : t('rep.healthNone')} />
        <Stat label={t('rep.growth')} value={pct(r.growth.median_height_change_pct)} note={r.growth.comparable_assets ? t('rep.growthNote', { count: r.growth.comparable_assets }) : t('rep.growthNone')} />
        <Stat label={t('rep.canopy')} value={r.canopy.area_m2 == null ? '—' : `${fmt.number(r.canopy.area_m2, { maximumFractionDigits: 1 })} m²`} note={r.canopy.trees_measured ? t('rep.canopyNote', { count: r.canopy.trees_measured }) : t('rep.canopyNone')} />
        <Stat label={t('rep.coverage')} value="—" note={t('rep.coverageNone')} />
      </section>
    </div>
  )
}

function impactFigures(r: ImpactReport, t: ReturnType<typeof useI18n>['t']): Figure[] {
  const s = (section: string, label: string, value: number | string | null, note?: string): Figure => ({ section, label, value, note })
  return [
    s(t('rep.planting'), t('rep.registered'), r.planting.registered),
    s(t('rep.planting'), t('rep.planted'), r.planting.planted),
    s(t('rep.planting'), t('rep.batches'), r.planting.batches_registered),
    s(t('rep.planting'), t('rep.plantsInBatches'), r.planting.plants_in_batches),
    ...r.planting.by_species.map((x) => s(t('rep.bySpecies'), x.name, x.count)),
    s(t('rep.survival'), t('rep.survivalRate'), r.survival.rate, `${r.survival.alive} alive, ${r.survival.dead} dead`),
    ...r.survival.by_species.map((x) => s(t('rep.survival'), x.species, x.rate, `${x.alive} alive, ${x.dead} dead`)),
    s(t('rep.healthyShare'), 'start', r.health.healthy_share_start, `${r.health.assets_compared} assets compared`),
    s(t('rep.healthyShare'), 'end', r.health.healthy_share_end),
    s(t('rep.growth'), t('rep.growth'), r.growth.median_height_change_pct, `${r.growth.comparable_assets} assets`),
    s(t('rep.canopy'), t('rep.canopy'), r.canopy.area_m2, 'calculated from measured canopy widths, assuming circular crowns'),
    s(t('rep.coverage'), t('rep.coverage'), null, r.coverage.reason),
  ]
}

/** Impact: green-cover outcomes from records (plantings, survival, health change, growth, canopy). */
export function ImpactPage() {
  const { ws } = useWorkspaceCtx()
  const { t, fmt } = useI18n()
  const period = usePeriod()
  const q = useImpact(ws, period.since)
  return (
    <ReportFrame title={t('rep.impactTitle')} subtitle={t('rep.impactSubtitle')} slug="impact" period={period} figures={q.data ? impactFigures(q.data, t) : null} summary={q.data ? impactSentence(q.data, t, fmt.number) : null}>
      <ImpactBody q={q} />
    </ReportFrame>
  )
}
