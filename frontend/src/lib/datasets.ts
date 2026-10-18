import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type {
  AgreementReport, ClaimReadiness, DatasetDetailRecord, DatasetItem, DatasetSampleRecord, ImportReport, LabelReviewRecord, LicencePolicy, Page,
  QualityReport, ReviewSummary, SplitRecord,
} from '../api/types'
import { qs } from './slice'

/**
 * Data hooks for the dataset catalog (Stage D). The server is the only authority: these hooks never decide who may do
 * what, and `enabled` only avoids requests that would be refused anyway.
 */
type Params = Record<string, string | number | boolean | null | undefined>
const base = (ws: string, path: string, params?: Params) => `/workspaces/${ws}/datasets${path}${qs(params)}`

export const useLicencePolicy = (ws: string) =>
  useQuery({ queryKey: [ws, 'dataset-policy'], queryFn: () => api<LicencePolicy>(base(ws, '/licence-policy')), staleTime: 600_000 })

export const useDatasets = (ws: string, params: Params = { limit: 200 }) =>
  useQuery({ queryKey: [ws, 'dataset-list', params], queryFn: () => api<Page<DatasetItem>>(base(ws, '', params)), retry: false })

export const useDataset = (ws: string, id: string) =>
  useQuery({ queryKey: [ws, 'dataset', id], queryFn: () => api<DatasetDetailRecord>(base(ws, `/${id}`)), retry: false })

export const useDatasetSamples = (ws: string, id: string, params: Params, enabled = true) =>
  useQuery({ queryKey: [ws, 'dataset-samples', id, params], queryFn: () => api<Page<DatasetSampleRecord>>(base(ws, `/${id}/samples`, params)), enabled, retry: false })

export const useSampleReviews = (ws: string, id: string, sampleId: string, enabled = true) =>
  useQuery({ queryKey: [ws, 'dataset-reviews', id, sampleId], queryFn: () => api<LabelReviewRecord[]>(base(ws, `/${id}/samples/${sampleId}/reviews`)), enabled, retry: false })

export const useReviewSummary = (ws: string, id: string, enabled = true) =>
  useQuery({ queryKey: [ws, 'dataset-review-summary', id], queryFn: () => api<ReviewSummary>(base(ws, `/${id}/review-summary`)), enabled, retry: false })

export const useDatasetQuality = (ws: string, id: string, enabled = true) =>
  useQuery({ queryKey: [ws, 'dataset-quality', id], queryFn: () => api<QualityReport>(base(ws, `/${id}/quality`)), enabled, retry: false })

export const useDatasetAgreement = (ws: string, id: string, enabled = true) =>
  useQuery({ queryKey: [ws, 'dataset-agreement', id], queryFn: () => api<AgreementReport>(base(ws, `/${id}/agreement`)), enabled, retry: false })

export const useDatasetSplits = (ws: string, id: string, enabled = true) =>
  useQuery({ queryKey: [ws, 'dataset-splits', id], queryFn: () => api<SplitRecord[]>(base(ws, `/${id}/splits`)), enabled, retry: false })

export const useClaimReadiness = (ws: string, id: string, enabled = true) =>
  useQuery({ queryKey: [ws, 'dataset-claims', id], queryFn: () => api<ClaimReadiness>(base(ws, `/${id}/claim-readiness`)), enabled, retry: false })

// ------------------------------------------------------------------ writes: each refreshes everything dataset-related
function useDatasetMutation<TIn, TOut>(ws: string, fn: (input: TIn) => Promise<TOut>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === ws && String(q.queryKey[1]).startsWith('dataset') }),
  })
}

export const useCreateDataset = (ws: string) =>
  useDatasetMutation(ws, (body: Record<string, unknown>) => api<DatasetDetailRecord>(base(ws, ''), { method: 'POST', body }))

export const useAddEvidence = (ws: string, id: string) =>
  useDatasetMutation(ws, (body: Record<string, unknown>) => api<DatasetDetailRecord>(base(ws, `/${id}/evidence`), { method: 'POST', body }))

/** The server decides: approval is refused with `blockers` while the evidence is incomplete, whatever this client sends. */
export const useTransitionDataset = (ws: string, id: string) =>
  useDatasetMutation(ws, (body: { to_status: string; note?: string }) => api<DatasetDetailRecord>(base(ws, `/${id}/transitions`), { method: 'POST', body }))

export const useReviewSample = (ws: string, id: string) =>
  useDatasetMutation(ws, (v: { sampleId: string; body: Record<string, unknown> }) =>
    api<LabelReviewRecord>(base(ws, `/${id}/samples/${v.sampleId}/reviews`), { method: 'POST', body: v.body }))

/** Validate (commit=false) or import (commit=true) a CSV. The server validates everything; the client never decides. */
export const useImportSamples = (ws: string, id: string) =>
  useDatasetMutation(ws, (body: { csv_text: string; commit: boolean }) =>
    api<ImportReport>(base(ws, `/${id}/samples/import`), { method: 'POST', body }))

export const useRegisterSample = (ws: string, id: string) =>
  useDatasetMutation(ws, (body: { samples: Record<string, unknown>[] }) =>
    api<{ registered: number }>(base(ws, `/${id}/samples`), { method: 'POST', body }))

export const useCreateSplit = (ws: string, id: string) =>
  useDatasetMutation(ws, (body: Record<string, unknown>) => api<SplitRecord>(base(ws, `/${id}/splits`), { method: 'POST', body }))
