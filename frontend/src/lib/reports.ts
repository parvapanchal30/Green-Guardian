import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { qs } from './slice'

/** Analytics and Impact reports (ADR-068): counts and shares of recorded events in a period. */
export interface Named { name: string; count: number }
export interface AnalyticsReport {
  method: 'statistical'
  since: string
  until: string
  issues: { opened: number; closed: number; still_open: number; opened_by_category: Record<string, number>; opened_by_severity: Record<string, number>; closed_by_outcome: Record<string, number>; median_days_to_close: number | null }
  tasks: { created: number; completed: number; cancelled: number; completed_with_due_date: number; completed_on_time: number; on_time_pct: number | null; overdue_now: number; completed_by_type: Record<string, number> }
  actions: { recorded: number; by_kind: Record<string, number>; top_products: Named[] }
  observations: { recorded: number; with_health_score: number; with_measurements: number; assets_observed: number; observers: number; by_kind: Record<string, number> }
  agent: { suggested: number; accepted: number; dismissed: number; expired: number; open_now: number; outcomes: Record<string, number> }
}
export interface ImpactReport {
  method: 'statistical'
  since: string
  until: string
  planting: { registered: number; planted: number; batches_registered: number; plants_in_batches: number; by_species: Named[] }
  survival: { alive: number; dead: number; rate: number | null; by_species: { species: string; alive: number; dead: number; rate: number | null }[] }
  health: { assets_compared: number; healthy_share_start: number | null; healthy_share_end: number | null }
  growth: { comparable_assets: number; median_height_change_pct: number | null }
  canopy: { trees_measured: number; area_m2: number | null }
  coverage: { available: false; reason: string }
}

export function monthsAgo(months: number, now = new Date()): string {
  const d = new Date(now)
  d.setMonth(d.getMonth() - months)
  return d.toISOString()
}

export const PERIODS = [1, 3, 6, 12, 24] as const

/** The chosen report period, in months back from when the page opened. */
export function usePeriod(initial = 12) {
  const [months, setMonths] = useState<number>(initial)
  const [opened] = useState(() => new Date())
  const since = useMemo(() => monthsAgo(months, opened), [months, opened])
  return { months, setMonths, since, until: opened.toISOString() }
}

export const useAnalytics = (ws: string, since: string) =>
  useQuery({ queryKey: [ws, 'tasks', 'report-analytics', since], queryFn: () => api<AnalyticsReport>(`/workspaces/${ws}/reports/analytics${qs({ since })}`) })

export const useImpact = (ws: string, since: string) =>
  useQuery({ queryKey: [ws, 'observations', 'report-impact', since], queryFn: () => api<ImpactReport>(`/workspaces/${ws}/reports/impact${qs({ since })}`) })
