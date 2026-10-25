import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { AssetHarvests, HarvestOverview, HarvestUnit } from '../api/types'
import { refreshWorkspaceData } from './slice'

/** Harvest records (ADR-056). Append-only on the server: a mistake is replaced by a manager's correction. */
export const useHarvests = (ws: string, assetId: string) =>
  useQuery({ queryKey: [ws, 'harvests', assetId], queryFn: () => api<AssetHarvests>(`/workspaces/${ws}/assets/${assetId}/harvests`) })

/** Every effective harvest of the workspace in a period (Harvests page). */
export const useHarvestOverview = (ws: string, params: { since?: string; asset_id?: string }) =>
  useQuery({
    queryKey: [ws, 'harvests', 'overview', params],
    queryFn: () => {
      const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString()
      return api<HarvestOverview>(`/workspaces/${ws}/harvests${q ? `?${q}` : ''}`)
    },
  })

export interface HarvestInput {
  quantity: number
  unit: HarvestUnit
  harvested_at?: string
  grade?: string
  note?: string
}

export function useRecordHarvest(ws: string, assetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: HarvestInput) => api<AssetHarvests>(`/workspaces/${ws}/assets/${assetId}/harvests`, { method: 'POST', body }),
    onSuccess: () => refreshWorkspaceData(qc, ws),
  })
}

export function useCorrectHarvest(ws: string, assetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: HarvestInput & { id: string; note: string }) =>
      api<AssetHarvests>(`/workspaces/${ws}/assets/${assetId}/harvests/${id}/correct`, { method: 'POST', body }),
    onSuccess: () => refreshWorkspaceData(qc, ws),
  })
}

export const UNIT_LABEL: Record<HarvestUnit, string> = { kg: 'kg', t: 't', count: 'pieces', l: 'litres' }
