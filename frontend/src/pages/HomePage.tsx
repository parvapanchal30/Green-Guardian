import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { RecommendationCard } from '../components/RecommendationCard'
import { StatusChip } from '../components/StatusChip'
import { EmptyState, ErrorState, LoadingBlock } from '../components/states'
import { input } from '../components/domain'
import { useI18n, type TKey } from '../i18n'
import { atLeast } from '../lib/format'
import { useDashboard, useLocations, useRecommendations } from '../lib/slice'

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
  const { t, te, fmt } = useI18n()
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
        <p className="text-ink-2">{t(`mode.${workspace.mode}` as TKey)} · {t(`mode.audience.${workspace.mode}` as TKey)}</p>
      </header>

      <section aria-labelledby="state">
        <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
          <h2 id="state" className="text-lg font-semibold">{t('dash.currentState')}</h2>
          <div className="flex flex-wrap gap-2 text-sm">
            <label className="flex items-center gap-1">{t('dash.location')}
              <select aria-label={t('dash.filterLocation')} value={locationId} onChange={(e) => setLocationId(e.target.value)} className={input}>
                <option value="">{t('dash.all')}</option>
                {locations.data?.items.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-1">{t('dash.type')}
              <select aria-label={t('dash.filterType')} value={kind} onChange={(e) => setKind(e.target.value)} className={input}>
                <option value="">{t('dash.all')}</option>
                {KINDS.map((k) => <option key={k} value={k}>{te('kind', k)}</option>)}
              </select>
            </label>
          </div>
        </div>
        {dash.isLoading && <LoadingBlock label={t('dash.loading')} />}
        {dash.error && <ErrorState error={dash.error} onRetry={() => dash.refetch()} />}
        {d && d.assets.total === 0 && (
          <EmptyState title={filtered ? t('dash.empty.filtered') : t('dash.empty.none')} action={!filtered && atLeast(workspace.role, 'worker') ? <Link to={`/w/${ws}/assets`} className="text-moss underline">{t('dash.empty.register')}</Link> : undefined}>
            {d.assets.exited > 0 && !filtered
              ? t('dash.empty.allExited', { count: d.assets.exited })
              : filtered ? t('dash.empty.clearFilter') : t('dash.empty.hint')}
          </EmptyState>
        )}
        {d && d.assets.total > 0 && (
          <div className="space-y-4">
            <ul className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <Tile name={t('dash.tile.assets')} value={fmt.number(d.assets.total)} />
              <Tile name={te('health', 'healthy')} value={fmt.number(d.assets.health.healthy)} />
              <Tile name={te('health', 'at_risk')} value={fmt.number(d.assets.health.at_risk)} />
              <Tile name={te('health', 'critical')} value={fmt.number(d.assets.health.critical)} />
              <Tile name={t('dash.tile.openIssues')} value={fmt.number(d.work.open_issues)} />
              <Tile name={t('dash.tile.openTasks')} value={fmt.number(d.work.open_tasks)} />
              {d.assets.health.unknown > 0 && <Tile name={t('dash.tile.noHealth')} value={fmt.number(d.assets.health.unknown)} hint={t('dash.tile.noHealthHint')} />}
              {d.assets.exited > 0 && <Tile name={t('dash.tile.exited')} value={fmt.number(d.assets.exited)} hint={t('dash.tile.exitedHint')} />}
            </ul>
            <ul aria-label={t('dash.attentionList')} className="grid gap-3 sm:grid-cols-3">
              <Tile name={t('dash.tile.overdue')} value={fmt.number(d.work.overdue_tasks)} hint={t('dash.tile.overdueHint', { count: d.work.tasks_due_next_7_days })} />
              <Tile name={t('dash.tile.inspections')} value={fmt.number(d.work.inspections_due)} hint={t('dash.tile.inspectionsHint', { days: d.work.inspection_interval_days })} />
              <Tile name={t('dash.tile.suggestions')} value={fmt.number(d.work.open_recommendations)} />
            </ul>
          </div>
        )}
        {d && (
          <details className="mt-3 text-sm text-ink-2">
            <summary className="cursor-pointer">{d.kpis.map((k) => te('kpi', k.key, k.label)).join(' → ')}</summary>
            <ul className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {d.kpis.map((k) => (
                <li key={k.key} className="rounded border border-line p-2">
                  <span className="font-medium">{te('kpi', k.key, k.label)}</span>
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
          <h2 id="activity" className="mb-2 text-lg font-semibold">{t('dash.recent')}</h2>
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface text-sm">
            {d.recent_activity.map((a) => (
              <li key={`${a.type}-${a.ref_id}-${a.at}`} className="flex flex-wrap items-baseline justify-between gap-x-3 p-2">
                <span>
                  <Link className="text-moss underline" to={a.type === 'issue' ? `/w/${ws}/issues/${a.ref_id}` : a.asset_id ? `/w/${ws}/assets/${a.asset_id}` : `/w/${ws}/tasks`}>{a.title}</Link>
                  {a.detail && <span className="text-ink-2"> · {a.detail}</span>}
                </span>
                <time className="text-xs text-ink-3" dateTime={a.at}>{fmt.dateTime(a.at)}</time>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="attention">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 id="attention" className="text-lg font-semibold">{t('dash.attention')}</h2>
          <Link to={`/w/${ws}/ai/agent`} className="text-sm text-moss underline">{t('dash.agentLink')}</Link>
        </div>
        {recs.isLoading && <LoadingBlock label={t('dash.loadingSuggestions')} />}
        {recs.error && <ErrorState error={recs.error} onRetry={() => recs.refetch()} />}
        {recs.data?.total === 0 && <EmptyState title={t('dash.nothingToReview')}>{t('dash.nothingToReviewBody')}</EmptyState>}
        <ul className="space-y-2">{recs.data?.items.map((r) => <RecommendationCard key={r.id} rec={r} ws={ws} canDecide={canDecide} />)}</ul>
      </section>

      <section aria-labelledby="caps">
        <h2 id="caps" className="mb-2 text-lg font-semibold">{t('dash.live')}</h2>
        {!capabilities ? <LoadingBlock label={t('dash.loadingCapabilities')} /> : (
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">{t('dash.capabilitiesCaption')}</caption>
              <thead className="border-b border-line text-ink-2"><tr><th className="p-2 font-medium">{t('dash.cap.capability')}</th><th className="p-2 font-medium">{t('dash.cap.technique')}</th><th className="p-2 font-medium">{t('dash.cap.status')}</th></tr></thead>
              <tbody>
                {capabilities.map((cap) => (
                  <tr key={cap.key} className="border-b border-line last:border-0">
                    <td className="p-2">{cap.label}</td><td className="p-2 text-ink-2">{cap.technique}</td>
                    <td className="p-2">{cap.available ? <StatusChip tone="live">{t('dash.cap.live')}</StatusChip> : <StatusChip tone={cap.stage === 'mvp' ? 'building' : 'soon'}>{cap.stage === 'mvp' ? t('dash.cap.inDevelopment') : t('dash.cap.planned', { stage: cap.stage.toUpperCase() })}</StatusChip>}</td>
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
