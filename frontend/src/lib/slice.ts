import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { api, apiBlob } from '../api/client'
import type {
  AgentRun, Asset, Dashboard, Evidence, MapFeatureCollection, MapLayerInfo, Issue, IssueDetail, LocationItem, Observation, ObservationCreated, Page, Recommendation, RuleInfo,
  SpeciesItem, TaskDetail, Task, TimelineEvent, Workflow,
} from '../api/types'

/** Data hooks for the vertical slice. Query keys are [workspaceId, resource, ...] so one predicate can refresh a workspace. */

type Params = Record<string, string | number | boolean | null | undefined>

export function qs(params: Params = {}): string {
  const u = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') u.set(k, String(v))
  const s = u.toString()
  return s ? `?${s}` : ''
}

const base = (ws: string, path: string, params?: Params) => `/workspaces/${ws}${path}${qs(params)}`

/** Everything that can change after an observation, issue, task or recommendation action. */
const DATA = new Set(['assets', 'asset', 'timeline', 'observations', 'issues', 'issue', 'tasks', 'task', 'recommendations', 'dashboard', 'map', 'evidence'])
export function refreshWorkspaceData(qc: QueryClient, ws: string) {
  return qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === ws && DATA.has(String(q.queryKey[1])) })
}

// ------------------------------------------------------------------ reads
export const useAssets = (ws: string, params: Params) =>
  useQuery({ queryKey: [ws, 'assets', params], queryFn: () => api<Page<Asset>>(base(ws, '/assets', params)) })

export const useAsset = (ws: string, id: string) =>
  useQuery({ queryKey: [ws, 'asset', id], queryFn: () => api<Asset>(base(ws, `/assets/${id}`)) })

export const useTimeline = (ws: string, id: string) =>
  useQuery({ queryKey: [ws, 'timeline', id], queryFn: () => api<TimelineEvent[]>(base(ws, `/assets/${id}/timeline`)) })

export const useObservations = (ws: string, assetId: string) =>
  useQuery({
    queryKey: [ws, 'observations', assetId],
    queryFn: () => api<Page<Observation>>(base(ws, '/observations', { asset_id: assetId, limit: 20 })),
  })

export const useLocations = (ws: string) =>
  useQuery({ queryKey: [ws, 'locations'], queryFn: () => api<Page<LocationItem>>(base(ws, '/locations', { limit: 200 })) })

export const useSpecies = (ws: string) =>
  useQuery({ queryKey: [ws, 'species'], queryFn: () => api<Page<SpeciesItem>>(base(ws, '/species', { limit: 200 })), staleTime: 300_000 })

export const useIssues = (ws: string, params: Params) =>
  useQuery({ queryKey: [ws, 'issues', params], queryFn: () => api<Page<Issue>>(base(ws, '/issues', params)) })

export const useIssue = (ws: string, id: string) =>
  useQuery({ queryKey: [ws, 'issue', id], queryFn: () => api<IssueDetail>(base(ws, `/issues/${id}`)) })

export const useWorkflows = (ws: string) =>
  useQuery({ queryKey: [ws, 'workflows'], queryFn: () => api<Workflow[]>(base(ws, '/issues/workflows')), staleTime: 600_000 })

export const useTasks = (ws: string, params: Params) =>
  useQuery({ queryKey: [ws, 'tasks', params], queryFn: () => api<Page<Task>>(base(ws, '/tasks', params)) })

export const useRecommendations = (ws: string, params: Params = { status: 'open' }) =>
  useQuery({ queryKey: [ws, 'recommendations', params], queryFn: () => api<Page<Recommendation>>(base(ws, '/recommendations', params)) })

export const useAgentRules = (ws: string) =>
  useQuery({ queryKey: [ws, 'agent-rules'], queryFn: () => api<RuleInfo[]>(base(ws, '/agent/rules')) })

/** One backend read model: every figure is aggregated in the database, never summed from lists in the browser. */
export const useDashboard = (ws: string, params: Params = {}) =>
  useQuery({ queryKey: [ws, 'dashboard', params], queryFn: () => api<Dashboard>(base(ws, '/dashboard', params)) })

export const useMapLayers = (ws: string) =>
  useQuery({ queryKey: [ws, 'map-layers'], queryFn: () => api<MapLayerInfo[]>(base(ws, '/map/layers')), staleTime: 600_000 })

/** Features of one map layer, filtered and scoped by the server (PostGIS). */
export const useMapLayer = (ws: string, layer: string, params: Params) =>
  useQuery({ queryKey: [ws, 'map', layer, params], queryFn: () => api<MapFeatureCollection>(base(ws, `/map/layers/${layer}`, params)) })

export const useEvidence = (ws: string, params: Params) =>
  useQuery({ queryKey: [ws, 'evidence', params], queryFn: () => api<Page<Evidence>>(base(ws, '/evidence', params)) })

/** The image itself: protected, so fetched with the token and cached by (immutable) evidence id. */
export const useEvidenceBlob = (ws: string, ev: Evidence) =>
  useQuery({ queryKey: [ws, 'evidence-blob', ev.id], queryFn: () => apiBlob(ev.content_path), staleTime: Infinity, gcTime: 600_000 })

// ------------------------------------------------------------------ writes (each refreshes the affected workspace data)
function useWsMutation<TIn, TOut>(ws: string, fn: (input: TIn) => Promise<TOut>) {
  const qc = useQueryClient()
  return useMutation({ mutationFn: fn, onSuccess: () => refreshWorkspaceData(qc, ws) })
}

export const useCreateAsset = (ws: string) =>
  useWsMutation(ws, (body: Record<string, unknown>) => api<Asset>(base(ws, '/assets'), { method: 'POST', body }))

export function useCreateLocation(ws: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; kind: string }) => api<LocationItem>(base(ws, '/locations'), { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [ws, 'locations'] }),
  })
}

export const useCreateObservation = (ws: string) =>
  useWsMutation(ws, (body: Record<string, unknown>) => api<ObservationCreated>(base(ws, '/observations'), { method: 'POST', body }))

export const useCreateIssue = (ws: string) =>
  useWsMutation(ws, (body: Record<string, unknown>) => api<IssueDetail>(base(ws, '/issues'), { method: 'POST', body }))

export const useTransitionIssue = (ws: string, id: string) =>
  useWsMutation(ws, (body: Record<string, unknown>) => api<IssueDetail>(base(ws, `/issues/${id}/transitions`), { method: 'POST', body }))

export const useUpdateIssue = (ws: string, id: string) =>
  useWsMutation(ws, (body: Record<string, unknown>) => api<IssueDetail>(base(ws, `/issues/${id}`), { method: 'PATCH', body }))

export const useCreateTask = (ws: string) =>
  useWsMutation(ws, (body: Record<string, unknown>) => api<TaskDetail>(base(ws, '/tasks'), { method: 'POST', body }))

export const useTransitionTask = (ws: string) =>
  useWsMutation(ws, (v: { id: string; body: Record<string, unknown> }) =>
    api<TaskDetail>(base(ws, `/tasks/${v.id}/transitions`), { method: 'POST', body: v.body }))

export const useRunAgent = (ws: string) => useWsMutation(ws, () => api<AgentRun>(base(ws, '/agent/run'), { method: 'POST' }))

export const useAcceptRecommendation = (ws: string) =>
  useWsMutation(ws, (v: { id: string; body: Record<string, unknown> }) =>
    api<Recommendation>(base(ws, `/recommendations/${v.id}/accept`), { method: 'POST', body: v.body }))

export const useDismissRecommendation = (ws: string) =>
  useWsMutation(ws, (v: { id: string; reason: string }) =>
    api<Recommendation>(base(ws, `/recommendations/${v.id}/dismiss`), { method: 'POST', body: { reason: v.reason } }))

export const useUploadEvidence = (ws: string) =>
  useWsMutation(ws, (input: { assetId: string; file: File; caption?: string; observationId?: string; issueId?: string }) => {
    const f = new FormData()
    f.set('asset_id', input.assetId)
    f.set('file', input.file)
    if (input.caption?.trim()) f.set('caption', input.caption.trim())
    if (input.observationId) f.set('observation_id', input.observationId)
    if (input.issueId) f.set('issue_id', input.issueId)
    return api<Evidence>(base(ws, '/evidence'), { method: 'POST', body: f })
  })

export const useDeleteEvidence = (ws: string) =>
  useWsMutation(ws, (id: string) => api<void>(base(ws, `/evidence/${id}`), { method: 'DELETE' }))
