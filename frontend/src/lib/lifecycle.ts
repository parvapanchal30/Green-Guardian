import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { AssetLifecycle, LifecycleTemplate } from '../api/types'
import { refreshWorkspaceData } from './slice'

/** Lifecycle hooks (ADR-055). The server decides what is allowed; the browser only offers what the server listed. */
export const useLifecycle = (ws: string, assetId: string) =>
  useQuery({ queryKey: [ws, 'lifecycle', assetId], queryFn: () => api<AssetLifecycle>(`/workspaces/${ws}/assets/${assetId}/lifecycle`) })

export const useLifecycleTemplate = (ws: string, enabled: boolean) =>
  useQuery({
    queryKey: [ws, 'lifecycle-template'],
    queryFn: () => api<LifecycleTemplate>(`/workspaces/${ws}/lifecycle-template`),
    enabled,
    staleTime: 600_000,
  })

export interface StageChange {
  stage: string
  entered_at?: string
  note?: string
  correction?: boolean
}

export function useRecordStage(ws: string, assetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: StageChange) => api<AssetLifecycle>(`/workspaces/${ws}/assets/${assetId}/lifecycle`, { method: 'POST', body }),
    onSuccess: () => refreshWorkspaceData(qc, ws),
  })
}

/** A date input value (YYYY-MM-DD) as the API wants it. Today (or nothing) means "now": a time later today would be rejected as the future. */
export function enteredAt(date: string, today = new Date()): string | undefined {
  if (!date) return undefined
  const local = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  return date === local ? undefined : `${date}T12:00:00Z`
}
