import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { WorkspaceMode } from '../api/types'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { useI18n, type TKey } from '../i18n'
import { useAuth } from '../lib/auth'
import { useCreateWorkspace, useWorkspaces } from '../lib/queries'

const MODES: WorkspaceMode[] = ['green_management', 'agricultural_production']
/** Headline figures per mode, in order (the dashboard computes them; see docs/PRD.md section 5). */
const MODE_KPIS: Record<WorkspaceMode, string[]> = {
  green_management: ['survival', 'health', 'growth', 'canopy', 'coverage'],
  agricultural_production: ['growth', 'health', 'yield', 'harvest', 'revenue'],
}

export function WorkspacesPage() {
  const { t, te } = useI18n()
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
          <LanguageSwitcher />
          <button type="button" onClick={() => logout()} className="rounded border border-line px-2 py-1 hover:bg-surface-2">{t('nav.signOut')}</button>
        </div>
      </header>

      <section aria-labelledby="mine">
        <h2 id="mine" className="mb-3 text-lg font-semibold">{t('workspaces.yours')}</h2>
        {list.isLoading && <LoadingBlock label={t('workspaces.yours')} />}
        {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
        {list.data?.length === 0 && <EmptyState title={t('workspaces.none')}>{t('workspaces.noneBody')}</EmptyState>}
        <ul className="grid gap-3 sm:grid-cols-2">
          {list.data?.map((w) => (
            <li key={w.id}>
              <Link to={`/w/${w.id}`} className="block rounded-lg border border-line bg-surface p-4 hover:bg-surface-2">
                <p className="font-medium">{w.name}</p>
                <p className="text-sm text-ink-2">{t(`mode.${w.mode}` as TKey)} · {te('role', w.role)}</p>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="new" className="rounded-lg border border-line bg-surface p-4 md:p-6">
        <h2 id="new" className="mb-1 text-lg font-semibold">{t('workspaces.create')}</h2>
        <p className="mb-4 text-sm text-ink-2">{t('workspaces.createBody')}</p>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label htmlFor="name" className="mb-1 block text-sm text-ink-2">{t('workspaces.name')}</label>
            <input id="name" name="name" required maxLength={200} className="w-full rounded border border-line bg-canvas px-2 py-1.5" placeholder={t('workspaces.namePlaceholder')} />
          </div>
          <fieldset className="grid gap-3 sm:grid-cols-2">
            <legend className="mb-1 text-sm text-ink-2">{t('workspaces.mode')}</legend>
            {MODES.map((m) => {
              return (
                <label key={m} className={`cursor-pointer rounded-lg border p-3 text-sm ${mode === m ? 'border-moss bg-surface-2' : 'border-line'}`}>
                  <input type="radio" name="mode" value={m} checked={mode === m} onChange={() => setMode(m)} className="mr-2" />
                  <span className="font-medium">{t(`mode.${m}` as TKey)}</span>
                  <span className="mt-1 block text-ink-2">{t(`mode.audience.${m}` as TKey)}</span>
                  <span className="mt-2 block text-xs text-ink-3">{t('workspaces.kpis', { list: MODE_KPIS[m].map((k) => te('kpi', k)).join(' → ') })}</span>
                </label>
              )
            })}
          </fieldset>
          {create.error && <p role="alert" className="text-sm text-critical">{errorMessage(create.error)}</p>}
          <button disabled={create.isPending} className="rounded bg-moss px-4 py-2 text-moss-ink disabled:opacity-60">{create.isPending ? t('auth.creating') : t('workspaces.createButton')}</button>
        </form>
      </section>
    </div>
  )
}
