import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { WorkspaceMode } from '../api/types'
import { Icon, type IconName } from '../components/icons'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { Tag } from '../components/ui'
import { useI18n, type TKey } from '../i18n'
import { useAuth } from '../lib/auth'
import { useCreateWorkspace, useWorkspaces } from '../lib/queries'

const MODES: WorkspaceMode[] = ['green_management', 'agricultural_production']
/** Headline figures per mode, in order (the dashboard computes them; see docs/PRD.md section 5). */
const MODE_KPIS: Record<WorkspaceMode, string[]> = {
  green_management: ['survival', 'health', 'growth', 'canopy', 'coverage'],
  agricultural_production: ['growth', 'health', 'yield', 'harvest', 'revenue'],
}
const MODE_ICON: Record<WorkspaceMode, { icon: IconName; cls: string }> = {
  green_management: { icon: 'assets', cls: 'bg-moss-soft text-moss' },
  agricultural_production: { icon: 'harvests', cls: 'bg-surface-2 text-soil' },
}

function greeting(hour: number): TKey {
  return hour < 12 ? 'workspaces.morning' : hour < 17 ? 'workspaces.afternoon' : 'workspaces.evening'
}

/** Your workspaces and a new one (ADR-074): the list first, creation beside it. */
export function WorkspacesPage() {
  const { t, te } = useI18n()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const list = useWorkspaces()
  const create = useCreateWorkspace()
  const [mode, setMode] = useState<WorkspaceMode>('green_management')
  const [hour] = useState(() => new Date().getHours())
  const first = user?.name?.split(/[\s(]/)[0] ?? ''

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const name = String(new FormData(e.currentTarget).get('name') ?? '').trim()
    if (!name) return
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
    const ws = await create.mutateAsync({ name, mode, timezone: tz }).catch(() => null)
    if (ws) navigate(`/w/${ws.id}`)
  }

  return (
    <div className="min-h-screen bg-canvas">
      <header className="flex h-15 items-center gap-3 border-b border-line bg-surface px-4 sm:px-10">
        <span className="flex h-[30px] w-[30px] items-center justify-center rounded-md bg-moss text-moss-ink"><Icon name="comingNext" size={17} /></span>
        <span className="font-display text-xl font-bold">GreenGuardian</span>
        <div className="ml-auto flex items-center gap-3 text-sm">
          <span className="hidden text-ink-2 sm:inline">{user?.name}</span>
          <LanguageSwitcher className="bg-surface" />
          <button type="button" onClick={() => logout()} className="inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 hover:bg-surface-2">
            <Icon name="signOut" size={16} />
            {t('nav.signOut')}
          </button>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl items-start gap-8 px-4 py-9 sm:px-10 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <section aria-labelledby="mine" className="flex flex-col gap-3">
          <span className="font-mono text-[11px] tracking-[.08em] text-soil uppercase">{t(greeting(hour), { name: first })}</span>
          <h1 id="mine" className="text-[34px] leading-tight font-bold">{t('workspaces.yours')}</h1>
          {list.isLoading && <LoadingBlock label={t('workspaces.yours')} />}
          {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
          {list.data?.length === 0 && <EmptyState icon="assets" title={t('workspaces.none')}>{t('workspaces.noneBody')}</EmptyState>}
          {!!list.data?.length && (
            <ul className="overflow-hidden rounded-lg border border-line bg-surface">
              {list.data.map((w) => (
                <li key={w.id} className="border-b border-line-soft last:border-0">
                  <Link to={`/w/${w.id}`} className="grid grid-cols-[44px_minmax(0,1fr)_auto] items-center gap-4 px-5 py-4 hover:bg-surface-2/60">
                    <span className={`flex h-11 w-11 items-center justify-center rounded-lg ${MODE_ICON[w.mode].cls}`}><Icon name={MODE_ICON[w.mode].icon} size={22} /></span>
                    <span className="flex min-w-0 flex-col gap-1">
                      <b className="font-display text-xl">{w.name}</b>
                      <span className="flex flex-wrap items-center gap-2 text-[13.5px] text-ink-2">
                        <Tag>{t(`mode.${w.mode}` as TKey)}</Tag>
                        {te('role', w.role)}
                      </span>
                    </span>
                    <Icon name="next" size={18} className="text-ink-2" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="new" className="rounded-lg border border-line bg-surface p-5 lg:mt-[52px]">
          <h2 id="new" className="text-[22px] font-semibold">{t('workspaces.create')}</h2>
          <form onSubmit={submit} className="mt-3 flex flex-col gap-4">
            <div>
              <label htmlFor="name" className="mb-1.5 block text-sm font-semibold">{t('workspaces.name')}</label>
              <input id="name" name="name" required maxLength={200} className="w-full rounded-md border border-line bg-surface px-3 py-2" placeholder={t('workspaces.namePlaceholder')} />
            </div>
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-2 text-sm font-semibold">{t('workspaces.mode')}</legend>
              {MODES.map((m) => (
                <label key={m} className={`flex cursor-pointer flex-col gap-1 rounded-lg border-[1.5px] px-3.5 py-3 text-sm ${mode === m ? 'border-moss bg-moss-soft/40' : 'border-line'}`}>
                  <span className="flex items-center gap-2">
                    <input type="radio" name="mode" value={m} checked={mode === m} onChange={() => setMode(m)} className="accent-moss" />
                    <b className="text-[15px]">{t(`mode.${m}` as TKey)}</b>
                  </span>
                  <span className="text-ink-2">{t(`mode.audience.${m}` as TKey)}</span>
                  <span className="font-mono text-[11px] text-ink-2 uppercase">{MODE_KPIS[m].map((k) => te('kpi', k)).join(' · ')}</span>
                </label>
              ))}
            </fieldset>
            <p className="text-[13px] text-ink-2">{t('workspaces.createBody')}</p>
            {create.error && <p role="alert" className="text-sm text-critical">{errorMessage(create.error)}</p>}
            <button disabled={create.isPending} className="self-start rounded-md bg-moss px-4 py-2 font-semibold text-moss-ink hover:opacity-90 disabled:opacity-60">
              {create.isPending ? t('auth.creating') : t('workspaces.createButton')}
            </button>
          </form>
        </section>
      </main>
    </div>
  )
}
