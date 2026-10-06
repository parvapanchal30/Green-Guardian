import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { WorkspaceMode } from '../api/types'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { useAuth } from '../lib/auth'
import { useCreateWorkspace, useWorkspaces } from '../lib/queries'
import { VOCABULARY } from '../lib/vocabulary'

const MODES: WorkspaceMode[] = ['green_management', 'agricultural_production']

export function WorkspacesPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const list = useWorkspaces()
  const create = useCreateWorkspace()
  const [mode, setMode] = useState<WorkspaceMode>('green_management')

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const name = String(new FormData(e.currentTarget).get('name') ?? '').trim()
    if (!name) return
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
    const ws = await create.mutateAsync({ name, mode, timezone: tz }).catch(() => null)
    if (ws) navigate(`/w/${ws.id}`)
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-4 md:p-8">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight text-moss">GreenGuardian</h1>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-ink-2">{user?.name}</span>
          <button type="button" onClick={() => logout()} className="rounded border border-line px-2 py-1 hover:bg-surface-2">Sign out</button>
        </div>
      </header>

      <section aria-labelledby="mine">
        <h2 id="mine" className="mb-3 text-lg font-semibold">Your workspaces</h2>
        {list.isLoading && <LoadingBlock label="Loading workspaces" />}
        {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
        {list.data?.length === 0 && <EmptyState title="No workspaces yet">Create your first workspace below to start registering assets.</EmptyState>}
        <ul className="grid gap-3 sm:grid-cols-2">
          {list.data?.map((w) => (
            <li key={w.id}>
              <Link to={`/w/${w.id}`} className="block rounded-lg border border-line bg-surface p-4 hover:bg-surface-2">
                <p className="font-medium">{w.name}</p>
                <p className="text-sm text-ink-2">{VOCABULARY[w.mode].modeLabel} · {w.role}</p>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="new" className="rounded-lg border border-line bg-surface p-4 md:p-6">
        <h2 id="new" className="mb-1 text-lg font-semibold">Create a workspace</h2>
        <p className="mb-4 text-sm text-ink-2">One platform, two modes. The mode sets vocabulary, KPIs and lifecycle stages; the data model is the same.</p>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label htmlFor="name" className="mb-1 block text-sm text-ink-2">Workspace name</label>
            <input id="name" name="name" required maxLength={200} className="w-full rounded border border-line bg-canvas px-2 py-1.5" placeholder="e.g. City Green Cover, Nashik Farm" />
          </div>
          <fieldset className="grid gap-3 sm:grid-cols-2">
            <legend className="mb-1 text-sm text-ink-2">Operating mode</legend>
            {MODES.map((m) => {
              const v = VOCABULARY[m]
              return (
                <label key={m} className={`cursor-pointer rounded-lg border p-3 text-sm ${mode === m ? 'border-moss bg-surface-2' : 'border-line'}`}>
                  <input type="radio" name="mode" value={m} checked={mode === m} onChange={() => setMode(m)} className="mr-2" />
                  <span className="font-medium">{v.modeLabel}</span>
                  <span className="mt-1 block text-ink-2">{v.audience}</span>
                  <span className="mt-2 block text-xs text-ink-3">KPIs: {v.kpis.join(' → ')}</span>
                </label>
              )
            })}
          </fieldset>
          {create.error && <p role="alert" className="text-sm text-critical">{errorMessage(create.error)}</p>}
          <button disabled={create.isPending} className="rounded bg-moss px-4 py-2 text-moss-ink disabled:opacity-60">{create.isPending ? 'Creating…' : 'Create workspace'}</button>
        </form>
      </section>
    </div>
  )
}
