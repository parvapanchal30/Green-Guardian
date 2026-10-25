import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { ActionKind, ActionUnit, AssetActions } from '../api/types'
import { refreshWorkspaceData } from './slice'

/** Work done to assets (ADR-059). Append-only on the server: a mistake is replaced by a manager's correction. */
export const ACTION_KINDS: ActionKind[] = ['treat', 'water', 'fertilize', 'prune', 'pest_control', 'weed', 'mulch', 'replant', 'other']
export const ACTION_UNITS: ActionUnit[] = ['l', 'ml', 'kg', 'g', 'count']
export const MIN_REASON = 10

/** The action a completed task most likely stands for; inspections and monitoring are observations, not actions. */
export const KIND_FOR_TASK: Partial<Record<string, ActionKind>> = {
  treat: 'treat',
  water: 'water',
  fertilize: 'fertilize',
  prune: 'prune',
  plant: 'replant',
  replace: 'replant',
}

export const useActions = (ws: string, assetId: string) =>
  useQuery({ queryKey: [ws, 'actions', assetId], queryFn: () => api<AssetActions>(`/workspaces/${ws}/assets/${assetId}/actions`) })

export interface ActionInput {
  kind: ActionKind
  product?: string
  quantity?: number
  unit?: ActionUnit
  performed_at?: string
  note?: string
  issue_id?: string
  follow_up_days?: number
}

export function useRecordAction(ws: string, assetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ActionInput) => api<AssetActions>(`/workspaces/${ws}/assets/${assetId}/actions`, { method: 'POST', body }),
    onSuccess: () => refreshWorkspaceData(qc, ws),
  })
}

export interface ActionCorrection {
  id: string
  kind: ActionKind
  product?: string
  quantity?: number
  unit?: ActionUnit
  performed_at?: string
  withdrawn?: boolean
  note: string
}

export function useCorrectAction(ws: string, assetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: ActionCorrection) =>
      api<AssetActions>(`/workspaces/${ws}/assets/${assetId}/actions/${id}/correct`, { method: 'POST', body }),
    onSuccess: () => refreshWorkspaceData(qc, ws),
  })
}

/** Quantity and unit are given together or not at all; a blank quantity means "not measured". */
export function amount(quantityText: string, unit: string): { quantity?: number; unit?: ActionUnit } | 'invalid' {
  const q = quantityText.trim()
  if (q === '') return {}
  const n = Number(q)
  if (!Number.isFinite(n) || n <= 0) return 'invalid'
  return { quantity: n, unit: unit as ActionUnit }
}
