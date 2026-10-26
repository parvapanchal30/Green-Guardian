import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Asset, Issue, Page, Task } from '../api/types'
import { qs } from './slice'

export const SEARCH_MIN = 2

function useDebounced(value: string, ms = 250) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return v
}

/** Plants, issues and tasks matching the text, five of each, all scoped to this workspace by the API. */
export function useWorkspaceSearch(ws: string, text: string, kinds: ('assets' | 'issues' | 'tasks')[] = ['assets', 'issues', 'tasks']) {
  const q = useDebounced(text.trim())
  const on = q.length >= SEARCH_MIN
  const get = <T,>(path: string) => api<Page<T>>(`/workspaces/${ws}/${path}${qs({ q, limit: 5 })}`)
  const assets = useQuery({ queryKey: [ws, 'assets', 'search', q], queryFn: () => get<Asset>('assets'), enabled: on && kinds.includes('assets') })
  const issues = useQuery({ queryKey: [ws, 'issues', 'search', q], queryFn: () => get<Issue>('issues'), enabled: on && kinds.includes('issues') })
  const tasks = useQuery({ queryKey: [ws, 'tasks', 'search', q], queryFn: () => get<Task>('tasks'), enabled: on && kinds.includes('tasks') })
  return { q, on, loading: on && (assets.isFetching || issues.isFetching || tasks.isFetching), assets: assets.data?.items ?? [], issues: issues.data?.items ?? [], tasks: tasks.data?.items ?? [] }
}

