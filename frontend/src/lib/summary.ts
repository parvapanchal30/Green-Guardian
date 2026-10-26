import type { Dashboard } from '../api/types'
import type { TKey } from '../i18n'

type T = (key: TKey, params?: Record<string, string | number>) => string

/**
 * The sentence at the top of Home (ADR-069, idea 7): the dashboard figures put into words by a fixed template, in
 * the reader's language. It adds nothing that is not in the figures below it, and it is never written by a model.
 */
export function homeSummary(d: Dashboard, t: T): string {
  const h = d.assets.health
  const parts: string[] = []
  const living = d.assets.total
  parts.push(t('home.sum.health', { count: living, healthy: h.healthy, atRisk: h.at_risk, critical: h.critical }))
  if (h.unknown > 0) parts.push(t('home.sum.unknown', { count: h.unknown }))
  const overdue = d.work.overdue_tasks > 0 ? t('home.sum.overdue', { count: d.work.overdue_tasks }) : t('home.sum.noneOverdue')
  parts.push(t('home.sum.work', { tasks: t('home.sum.tasks', { count: d.work.open_tasks }), overdue, issues: t('home.sum.issues', { count: d.work.open_issues }) }))
  if (d.work.inspections_due > 0) parts.push(t('home.sum.look', { count: d.work.inspections_due, days: d.work.inspection_interval_days }))
  if (d.work.open_recommendations > 0) parts.push(t('home.sum.decide', { count: d.work.open_recommendations }))
  return parts.join(' ')
}

/** Group activity by local calendar day, newest first: "today", "yesterday", or the date. */
export function dayKey(iso: string, now = new Date()): 'today' | 'yesterday' | string {
  const d = new Date(iso)
  const day = (x: Date) => `${x.getFullYear()}-${x.getMonth()}-${x.getDate()}`
  if (day(d) === day(now)) return 'today'
  const y = new Date(now)
  y.setDate(now.getDate() - 1)
  if (day(d) === day(y)) return 'yesterday'
  return day(d)
}

export type DueGroup = 'overdue' | 'today' | 'week' | 'later' | 'none'
export const DUE_GROUPS: DueGroup[] = ['overdue', 'today', 'week', 'later', 'none']

/**
 * Where an open task sits on the Tasks page (ADR-073): overdue (as the server says), due today, within the next
 * seven days, later, or with no due date. Days are the reader's local calendar days.
 */
export function dueGroup(task: { due_at: string | null; overdue: boolean }, now = new Date()): DueGroup {
  if (task.overdue) return 'overdue'
  if (!task.due_at) return 'none'
  const start = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const days = Math.round((start(new Date(task.due_at)) - start(now)) / 86_400_000)
  if (days <= 0) return 'today'
  if (days <= 7) return 'week'
  return 'later'
}

type Num = (v: number, o?: Intl.NumberFormatOptions) => string

/**
 * The sentence before the Analytics figures (ADR-077, idea 7): the period's counts put into words by a fixed
 * template. It adds nothing that is not in the figures below it.
 */
export function analyticsSentence(r: import('./reports').AnalyticsReport, t: T, num: Num): string {
  const parts = [
    t('rep.sum.issues', { opened: num(r.issues.opened), closed: num(r.issues.closed), open: num(r.issues.still_open) }),
    r.tasks.on_time_pct == null
      ? t('rep.sum.tasks', { done: num(r.tasks.completed), created: num(r.tasks.created) })
      : t('rep.sum.tasksOnTime', { done: num(r.tasks.completed), created: num(r.tasks.created), pct: num(r.tasks.on_time_pct, { maximumFractionDigits: 0 }) }),
    t('rep.sum.observations', { count: r.observations.recorded, n: num(r.observations.recorded), plants: t('rep.sum.plants', { count: r.observations.assets_observed, n: num(r.observations.assets_observed) }) }),
  ]
  return parts.join(' ')
}

/** The sentence before the Impact figures: plantings, survival and the change in healthy share, from the report. */
export function impactSentence(r: import('./reports').ImpactReport, t: T, num: Num): string {
  const pct = (v: number) => num(v, { maximumFractionDigits: 1 })
  const parts = [t('rep.sum.planted', { count: r.planting.registered, n: num(r.planting.registered) })]
  if (r.survival.rate != null) parts.push(t('rep.sum.survival', { pct: pct(r.survival.rate), alive: num(r.survival.alive), dead: num(r.survival.dead) }))
  if (r.health.assets_compared && r.health.healthy_share_start != null && r.health.healthy_share_end != null) {
    parts.push(t('rep.sum.health', { from: pct(r.health.healthy_share_start), to: pct(r.health.healthy_share_end), count: r.health.assets_compared }))
  }
  if (r.growth.median_height_change_pct != null) parts.push(t('rep.sum.growth', { pct: pct(r.growth.median_height_change_pct), count: r.growth.comparable_assets }))
  return parts.join(' ')
}
