import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { qs } from './slice'

/** Health and growth over time (Monitor pages): descriptive figures from recorded observations only. */
export type GrowthMetric = 'height_cm' | 'girth_cm' | 'canopy_m'

export interface HealthWeek {
  week_start: string
  observations: number
  assets: number
  mean_score: number | null
  healthy: number
  at_risk: number
  critical: number
}
export interface HealthMonitor {
  method: 'statistical'
  weeks: number
  now: { healthy: number; at_risk: number; critical: number; no_data: number }
  weekly: HealthWeek[]
  declining: { asset_id: string; label: string; first_score: number; first_at: string; latest_score: number; latest_at: string; change: number }[]
  not_observed_days: number
  not_observed_count: number
  not_observed: { asset_id: string; label: string; last_observed_at: string | null }[]
}
export interface GrowthRow {
  asset_id: string
  label: string
  kind: string
  measurements: number
  first: number
  first_at: string
  latest: number
  latest_at: string
  change: number | null
  change_pct: number | null
  per_year: number | null
}
export interface GrowthMonitor {
  method: 'statistical'
  metric: GrowthMetric
  months: number
  min_span_days: number
  assets: GrowthRow[]
  measured_assets: number
  comparable_assets: number
  median_change_pct: number | null
}
export interface Measurement {
  observation_id: string
  observed_at: string
  height_cm: number | null
  girth_cm: number | null
  canopy_m: number | null
}

export const UNIT: Record<GrowthMetric, string> = { height_cm: 'cm', girth_cm: 'cm', canopy_m: 'm' }

export const useHealthMonitor = (ws: string, weeks: number) =>
  useQuery({ queryKey: [ws, 'observations', 'health-monitor', weeks], queryFn: () => api<HealthMonitor>(`/workspaces/${ws}/monitor/health${qs({ weeks })}`) })

export const useGrowthMonitor = (ws: string, metric: GrowthMetric, months: number) =>
  useQuery({
    queryKey: [ws, 'observations', 'growth-monitor', metric, months],
    queryFn: () => api<GrowthMonitor>(`/workspaces/${ws}/monitor/growth${qs({ metric, months })}`),
  })

export const useAssetGrowth = (ws: string, assetId: string) =>
  useQuery({
    queryKey: [ws, 'observations', 'growth', assetId],
    queryFn: () => api<{ asset_id: string; measurements: Measurement[] }>(`/workspaces/${ws}/assets/${assetId}/growth`),
  })
