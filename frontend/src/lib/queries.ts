import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Capability, Forecast, Member, Role, Workspace, WorkspaceMode } from '../api/types'

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

/** Member management (ADR-074). The server enforces who may do what; these only call it and refresh the list. */
export function useMemberChanges(ws: string) {
  const qc = useQueryClient()
  const done = () => qc.invalidateQueries({ queryKey: keys.members(ws) })
  return {
    add: useMutation({
      mutationFn: (body: { email: string; role: Role }) => api<Member>(`/workspaces/${ws}/members`, { method: 'POST', body }),
      onSuccess: done,
    }),
    changeRole: useMutation({
      mutationFn: ({ userId, role }: { userId: string; role: Role }) => api<Member>(`/workspaces/${ws}/members/${userId}`, { method: 'PATCH', body: { role } }),
      onSuccess: done,
    }),
    remove: useMutation({
      mutationFn: (userId: string) => api<void>(`/workspaces/${ws}/members/${userId}`, { method: 'DELETE' }),
      onSuccess: done,
    }),
  }
}

// ---- weather places (ADR-075)

export interface FoundPlace { name: string; region: string; latitude: number; longitude: number }
export interface SavedPlace { id: string; name: string; region: string | null; latitude: number; longitude: number }

/** Search places by name through the server (its configured provider's geocoder); asks only from 2 characters. */
export const usePlaceSearch = (ws: string, q: string) =>
  useQuery({
    queryKey: [ws, 'weather-places-search', q],
    queryFn: () => api<{ source: string; attribution: string; items: FoundPlace[] }>(`/workspaces/${ws}/weather/places/search?q=${encodeURIComponent(q)}`),
    enabled: q.trim().length >= 2,
    retry: false,
    staleTime: 600_000,
  })

export const useSavedPlaces = (ws: string) =>
  useQuery({ queryKey: [ws, 'weather-places'], queryFn: () => api<SavedPlace[]>(`/workspaces/${ws}/weather/places`) })

export function useWeatherPlaceChanges(ws: string) {
  const qc = useQueryClient()
  const done = () => qc.invalidateQueries({ queryKey: [ws, 'weather-places'] })
  return {
    save: useMutation({
      mutationFn: (body: Omit<SavedPlace, 'id'>) => api<SavedPlace>(`/workspaces/${ws}/weather/places`, { method: 'POST', body }),
      onSuccess: done,
    }),
    remove: useMutation({
      mutationFn: (id: string) => api<void>(`/workspaces/${ws}/weather/places/${id}`, { method: 'DELETE' }),
      onSuccess: done,
    }),
  }
}
