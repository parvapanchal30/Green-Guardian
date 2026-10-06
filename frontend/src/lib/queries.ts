import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Capability, Forecast, Member, Workspace, WorkspaceMode } from '../api/types'

// Query keys are workspace-scoped: [workspaceId, resource, params] (docs/FRONTEND_ARCHITECTURE.md).
export const keys = {
  workspaces: ['workspaces'] as const,
  workspace: (ws: string) => [ws, 'workspace'] as const,
  capabilities: (ws: string) => [ws, 'capabilities'] as const,
  members: (ws: string) => [ws, 'members'] as const,
  weather: (ws: string, lat: number, lon: number, days: number) => [ws, 'weather', lat, lon, days] as const,
}

export const useWorkspaces = () => useQuery({ queryKey: keys.workspaces, queryFn: () => api<Workspace[]>('/workspaces') })

export const useWorkspace = (ws: string) =>
  useQuery({ queryKey: keys.workspace(ws), queryFn: () => api<Workspace>(`/workspaces/${ws}`) })

export const useCapabilities = (ws: string) =>
  useQuery({ queryKey: keys.capabilities(ws), queryFn: () => api<Capability[]>(`/workspaces/${ws}/capabilities`) })

export const useMembers = (ws: string) =>
  useQuery({ queryKey: keys.members(ws), queryFn: () => api<Member[]>(`/workspaces/${ws}/members`) })

export function useForecast(ws: string, coords: { lat: number; lon: number; days: number } | null) {
  return useQuery({
    queryKey: keys.weather(ws, coords?.lat ?? 0, coords?.lon ?? 0, coords?.days ?? 0),
    queryFn: () => api<Forecast>(`/workspaces/${ws}/weather?lat=${coords!.lat}&lon=${coords!.lon}&days=${coords!.days}`),
    enabled: coords !== null,
    retry: false,
  })
}

export function useCreateWorkspace() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; mode: WorkspaceMode; timezone: string }) =>
      api<Workspace>('/workspaces', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.workspaces }),
  })
}
