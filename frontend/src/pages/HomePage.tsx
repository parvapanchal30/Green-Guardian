import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Dashboard, DashboardActivity, Task } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { PageHeader, btnPrimary, input } from '../components/domain'
import { Icon } from '../components/icons'
import { RecommendationCard } from '../components/RecommendationCard'
import { RecordPicker } from '../components/shell/RecordPicker'
import { EmptyState, ErrorState, LoadingBlock } from '../components/states'
import { Card, HealthBar, SectionHeading, StatTile, Tag } from '../components/ui'
import { useI18n, type TKey } from '../i18n'
import { atLeast } from '../lib/format'
import { useDashboard, useLocations, useRecommendations, useTasks } from '../lib/slice'
import { dayKey, homeSummary } from '../lib/summary'
import { activityText } from '../lib/recText'

const KINDS = ['tree', 'plant', 'shrub', 'crop_batch', 'other']
const SHOWN_SUGGESTIONS = 3

function activityLink(ws: string, a: DashboardActivity): string {
  if (a.type === 'issue') return `/w/${ws}/issues/${a.ref_id}`
  return a.asset_id ? `/w/${ws}/assets/${a.asset_id}` : `/w/${ws}/tasks`
}

/** Activity grouped by day, newest first; the record key (GG-001, T-004) leads each line when there is one. */
function Activity({ ws, items }: { ws: string; items: DashboardActivity[] }) {
  const { t, te, fmt, locale } = useI18n()
  const groups: { key: string; label: string; items: DashboardActivity[] }[] = []
  for (const a of items) {
    const k = dayKey(a.at)
    let g = groups.find((x) => x.key === k)
    if (!g) {
      const label = k === 'today' ? t('home.today') : k === 'yesterday' ? t('home.yesterday') : new Date(a.at).toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' })
      g = { key: k, label, items: [] }
      groups.push(g)
    }
    g.items.push(a)
  }
  return (
    <div className="flex flex-col gap-3">
      {groups.map((g) => (
        <div key={g.key}>
          <p className="mb-1 font-mono text-[11px] tracking-[0.08em] text-soil uppercase">{g.label}</p>
          <ul className="divide-y divide-line-soft text-sm">
            {g.items.map((a) => {
              const { title, detail } = activityText(a, t, te, fmt.number)
              return (
                <li key={`${a.type}-${a.ref_id}-${a.at}`} className="flex items-baseline gap-3 py-1.5">
                  <span className="min-w-16 shrink-0">{a.key ? <Tag tone={a.type === 'issue' ? 'critical' : 'neutral'}>{a.key}</Tag> : <Tag tone="moss">{te('timelineType', a.type)}</Tag>}</span>
                  <span className="min-w-0 flex-1">
                    <Link className="text-ink hover:underline" to={activityLink(ws, a)}>{title}</Link>
                    {detail && <span className="text-ink-2"> · {detail}</span>}
                  </span>
                  <time className="shrink-0 font-mono text-xs text-ink-2" dateTime={a.at}>{new Date(a.at).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })}</time>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </div>
  )
}

function DueNext({ ws }: { ws: string }) {
  const { t, locale } = useI18n()
  const tasks = useTasks(ws, { is_open: true, limit: 5 })
  const [now] = useState(() => Date.now())
  const due = (task: Task) => {
    if (!task.due_at) return { text: t('home.noDate'), soon: false }
    const d = new Date(task.due_at)
    const days = (d.getTime() - now) / 86_400_000
    return {
      text: days < 7 ? d.toLocaleDateString(locale, { weekday: 'short' }) : d.toLocaleDateString(locale, { day: 'numeric', month: 'short' }),
      soon: days < 2,
    }
  }
  if (tasks.isLoading) return <LoadingBlock />
  if (tasks.error) return <ErrorState error={tasks.error} onRetry={() => tasks.refetch()} />
  const items = tasks.data?.items ?? []
  return (
    <Card>
      {items.length === 0 && <p className="px-4 py-3 text-sm text-ink-2">{t('home.dueNextEmpty')}</p>}
      <ul className="divide-y divide-line-soft">
        {items.map((task) => {
          const d = due(task)
          return (
            <li key={task.id} className="flex items-baseline gap-3 px-4 py-2.5 text-sm">
              <span className={`w-14 shrink-0 font-mono text-xs ${d.soon ? 'text-at-risk' : 'text-ink-2'}`}>{d.text}</span>
              <span className="min-w-0 flex-1">
                {task.issue_id ? <Link to={`/w/${ws}/issues/${task.issue_id}`} className="text-ink hover:underline">{task.title}</Link> : task.asset_id ? <Link to={`/w/${ws}/assets/${task.asset_id}`} className="text-ink hover:underline">{task.title}</Link> : task.title}
              </span>
            </li>
          )
        })}
      </ul>
      <div className="border-t border-line-soft px-4 py-2 text-sm"><Link to={`/w/${ws}/tasks`} className="text-moss underline">{t('home.allTasks')}</Link></div>
    </Card>
  )
}

function Figures({ d }: { d: Dashboard }) {
  const { t, te, fmt } = useI18n()
  const available = d.kpis.filter((k) => k.available)
  const missing = d.kpis.filter((k) => !k.available)
  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="flex flex-col gap-2 rounded-lg border border-line bg-surface px-4 py-3 sm:col-span-2">
          <span className="text-[13px] text-ink-2">{t('home.living')}</span>
          <span className="font-display text-[28px] leading-tight font-bold">{fmt.number(d.assets.total)}</span>
          <HealthBar healthy={d.assets.health.healthy} atRisk={d.assets.health.at_risk} critical={d.assets.health.critical} noData={d.assets.health.unknown} />
          {d.assets.exited > 0 && <span className="text-xs text-ink-3">{t('home.exited', { count: d.assets.exited })}</span>}
        </div>
        <StatTile
          label={t('home.openWork')}
          value={fmt.number(d.work.open_tasks)}
          tone={d.work.overdue_tasks > 0 ? 'critical' : 'neutral'}
          note={t('home.openWorkNote', { overdue: d.work.overdue_tasks, due: d.work.tasks_due_next_7_days, issues: d.work.open_issues })}
        />
        <StatTile label={t('home.look')} value={fmt.number(d.work.inspections_due)} tone={d.work.inspections_due > 0 ? 'at-risk' : 'neutral'} note={t('home.lookNote', { days: d.work.inspection_interval_days })} />
        {available.map((k) => (
          <StatTile key={k.key} label={te('kpi', k.key, k.label)} value={`${k.value}${k.unit ?? ''}`} note={k.basis ?? undefined} />
        ))}
      </div>
      {missing.length > 0 && (
        <details className="text-sm text-ink-2">
          <summary className="cursor-pointer">{t('home.unavailable')}: {missing.map((k) => te('kpi', k.key, k.label)).join(', ')}</summary>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {missing.map((k) => (
              <li key={k.key} className="rounded-md border border-line-soft bg-surface px-3 py-2">
                <span className="font-medium text-ink">{te('kpi', k.key, k.label)}</span>
                <span className="block text-xs text-ink-3">{k.reason}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

/** Today (ADR-069 phase 3): what needs a decision first, then the state of the place in words and figures, then what happened and what is due. */
export function HomePage() {
  const { ws, workspace } = useWorkspaceCtx()
  const { t, te, locale } = useI18n()
  const [locationId, setLocationId] = useState('')
  const [kind, setKind] = useState('')
  const [picking, setPicking] = useState(false)
  const locations = useLocations(ws)
  const dash = useDashboard(ws, { location_id: locationId || undefined, kind: kind || undefined })
  const recs = useRecommendations(ws)
  const d = dash.data
  const canDecide = atLeast(workspace.role, 'manager')
  const canRecord = atLeast(workspace.role, 'worker')
  const filtered = Boolean(locationId || kind)
  const [opened] = useState(() => new Date())
  const today = opened.toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' })
  const suggestions = recs.data?.items ?? []

  return (
    <div className="flex flex-col gap-7">
      <PageHeader eyebrow={`${today} · ${t(`mode.${workspace.mode}` as TKey)}`} title={workspace.name} subtitle={t(`mode.audience.${workspace.mode}` as TKey)}>
        {canRecord && (
          <button type="button" className={btnPrimary} onClick={() => setPicking(true)} aria-haspopup="dialog">
            <Icon name="record" size={17} />
            {t('navx.record')}
          </button>
        )}
      </PageHeader>
      {picking && <RecordPicker ws={ws} onClose={() => setPicking(false)} />}

      <section aria-labelledby="attention">
        <SectionHeading id="attention" title={t('home.decide')}>
          {recs.data && recs.data.total > 0 && <span className="text-ink-2">{t('home.decideFrom', { count: recs.data.total })}</span>}
        </SectionHeading>
        {recs.isLoading && <LoadingBlock label={t('dash.loadingSuggestions')} />}
        {recs.error && <ErrorState error={recs.error} onRetry={() => recs.refetch()} />}
        {recs.data?.total === 0 && <EmptyState icon="check" title={t('dash.nothingToReview')}>{t('dash.nothingToReviewBody')}</EmptyState>}
        <ul className="flex flex-col gap-2">{suggestions.slice(0, SHOWN_SUGGESTIONS).map((r) => <RecommendationCard key={r.id} rec={r} ws={ws} canDecide={canDecide} />)}</ul>
        {suggestions.length > SHOWN_SUGGESTIONS && (
          <Link to={`/w/${ws}/ai/agent`} className="mt-2 inline-block text-sm font-medium text-moss underline">{t('home.more', { count: (recs.data?.total ?? suggestions.length) - SHOWN_SUGGESTIONS })}</Link>
        )}
      </section>

      <section aria-labelledby="state">
        <SectionHeading id="state" title={t('home.figures')}>
          <label className="flex items-center gap-1.5">{t('dash.location')}
            <select aria-label={t('dash.filterLocation')} value={locationId} onChange={(e) => setLocationId(e.target.value)} className={`${input} w-auto`}>
              <option value="">{t('dash.all')}</option>
              {locations.data?.items.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1.5">{t('dash.type')}
            <select aria-label={t('dash.filterType')} value={kind} onChange={(e) => setKind(e.target.value)} className={`${input} w-auto`}>
              <option value="">{t('dash.all')}</option>
              {KINDS.map((k) => <option key={k} value={k}>{te('kind', k)}</option>)}
            </select>
          </label>
        </SectionHeading>
        {dash.isLoading && <LoadingBlock label={t('dash.loading')} />}
        {dash.error && <ErrorState error={dash.error} onRetry={() => dash.refetch()} />}
        {d && d.assets.total === 0 && (
          <EmptyState icon="assets" title={filtered ? t('dash.empty.filtered') : t('dash.empty.none')} action={!filtered && canRecord ? <Link to={`/w/${ws}/assets`} className="text-moss underline">{t('dash.empty.register')}</Link> : undefined}>
            {d.assets.exited > 0 && !filtered ? t('dash.empty.allExited', { count: d.assets.exited }) : filtered ? t('dash.empty.clearFilter') : t('dash.empty.hint')}
          </EmptyState>
        )}
        {d && d.assets.total > 0 && (
          <div className="flex flex-col gap-3">
            <Card className="px-4 py-3">
              <p className="font-mono text-[10.5px] tracking-[0.06em] text-ink-2 uppercase">{t('home.sum.label')}</p>
              <p className="mt-1 font-display text-lg leading-snug font-semibold">{homeSummary(d, t)}</p>
            </Card>
            <Figures d={d} />
          </div>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <section aria-labelledby="activity">
          <SectionHeading id="activity" title={t('home.activity')} />
          {d && d.recent_activity.length > 0 ? <Activity ws={ws} items={d.recent_activity} /> : d && <p className="text-sm text-ink-2">—</p>}
        </section>
        <section aria-labelledby="due-next">
          <SectionHeading id="due-next" title={t('home.dueNext')} />
          <DueNext ws={ws} />
        </section>
      </div>
    </div>
  )
}
