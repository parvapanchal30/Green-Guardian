import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Page, ProtocolDetailRecord, ProtocolSummaryRecord, ProtocolTemplate } from '../api/types'

/** Evaluation-protocol registry hooks. The server computes every status; the client only displays it. */
const base = (ws: string, path = '') => `/workspaces/${ws}/evaluation-protocols${path}`

export const useProtocols = (ws: string) =>
  useQuery({ queryKey: [ws, 'protocol-list'], queryFn: () => api<Page<ProtocolSummaryRecord>>(`${base(ws)}?limit=100`), retry: false })

export const useProtocol = (ws: string, id: string) =>
  useQuery({ queryKey: [ws, 'protocol', id], queryFn: () => api<ProtocolDetailRecord>(base(ws, `/${id}`)), retry: false })

export const useProtocolTemplate = (ws: string, enabled: boolean) =>
  useQuery({ queryKey: [ws, 'protocol-template'], queryFn: () => api<ProtocolTemplate>(base(ws, '/template')), enabled, staleTime: 600_000, retry: false })

function useProtocolMutation<TIn, TOut>(ws: string, fn: (input: TIn) => Promise<TOut>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === ws && String(q.queryKey[1]).startsWith('protocol') }),
  })
}

export const useCreateProtocol = (ws: string) =>
  useProtocolMutation(ws, (body: { key: string; content: unknown }) => api<ProtocolDetailRecord>(base(ws), { method: 'POST', body }))

export const useSignoff = (ws: string, id: string) =>
  useProtocolMutation(ws, (body: Record<string, unknown>) => api<ProtocolDetailRecord>(base(ws, `/${id}/signoffs`), { method: 'POST', body }))
