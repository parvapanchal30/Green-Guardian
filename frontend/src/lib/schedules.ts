import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { GenerateResult, InspectionSchedule, ScheduleDetail } from '../api/types'
import { qs, refreshWorkspaceData } from './slice'

/** Recurring inspections (ADR-062). A manager sets the routine; the worker (or "Create due tasks now") makes the tasks. */
export const useSchedules = (ws: string, params: { asset_id?: string; location_id?: string; active?: boolean } = {}) =>
  useQuery({ queryKey: [ws, 'schedules', params], queryFn: () => api<InspectionSchedule[]>(`/workspaces/${ws}/schedules${qs(params)}`) })

export const useSchedule = (ws: string, id: string | null) =>
  useQuery({
    queryKey: [ws, 'schedule', id],
    queryFn: () => api<ScheduleDetail>(`/workspaces/${ws}/schedules/${id}`),
    enabled: id != null,
  })

export interface ScheduleInput {
  asset_id?: string
  location_id?: string
  title?: string
  task_type: 'inspect' | 'monitor'
  interval_days: number
  lead_days: number
  first_due_at?: string
  assignee_id?: string
  priority?: string
}

function useWs<TIn, TOut>(ws: string, fn: (input: TIn) => Promise<TOut>) {
  const qc = useQueryClient()
  return useMutation({ mutationFn: fn, onSuccess: () => refreshWorkspaceData(qc, ws) })
}

export const useCreateSchedule = (ws: string) =>
  useWs(ws, (body: ScheduleInput) => api<ScheduleDetail>(`/workspaces/${ws}/schedules`, { method: 'POST', body }))

export const useUpdateSchedule = (ws: string) =>
  useWs(ws, ({ id, ...body }: { id: string } & Record<string, unknown>) =>
    api<ScheduleDetail>(`/workspaces/${ws}/schedules/${id}`, { method: 'PATCH', body }))

export const useGenerateDue = (ws: string) =>
  useWs(ws, () => api<GenerateResult>(`/workspaces/${ws}/schedules/generate`, { method: 'POST' }))

/** A whole number of days in 1..max, or null. */
export function days(text: string, max: number, min = 1): number | null {
  const n = Number(text.trim())
  return Number.isInteger(n) && n >= min && n <= max ? n : null
}
