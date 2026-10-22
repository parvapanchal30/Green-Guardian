import { useState } from 'react'
import { Link, NavLink, Navigate, Outlet, useNavigate, useOutletContext, useParams } from 'react-router-dom'
import type { Capability, Workspace } from '../api/types'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { StatusChip } from '../components/StatusChip'
import { TourButton } from '../components/TourPanel'
import { ErrorState, LoadingBlock } from '../components/states'
import { useI18n, type TKey } from '../i18n'
import { useAuth } from '../lib/auth'
import { useCapabilities, useWorkspace, useWorkspaces } from '../lib/queries'
import { navFor, pathFor, routeKey, statusLabel } from './routes'


export interface WorkspaceCtx {
  ws: string
  workspace: Workspace
  capabilities: Capability[] | undefined
}
export const useWorkspaceCtx = () => useOutletContext<WorkspaceCtx>()

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status } = useAuth()
  const { t } = useI18n()
  if (status === 'loading') return <div className="p-8"><LoadingBlock label={t('common.restoringSession')} /></div>
  if (status === 'anon') return <Navigate to="/login" replace />
  return <>{children}</>
}

export function WorkspaceLayout() {
  const { t, te } = useI18n()
  const { ws = '' } = useParams()
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const wsQuery = useWorkspace(ws)
  const caps = useCapabilities(ws)
  const all = useWorkspaces()
  const [open, setOpen] = useState(false)

  if (wsQuery.isLoading) return <div className="p-8"><LoadingBlock label={t('nav.switchWorkspace')} /></div>
  if (wsQuery.error || !wsQuery.data)
    return (
      <div className="mx-auto max-w-xl p-8 space-y-4">
        <ErrorState error={wsQuery.error ?? new Error(t('common.workspaceNotFound'))} onRetry={() => wsQuery.refetch()} />
        <Link to="/" className="text-moss underline">{t('nav.backToWorkspaces')}</Link>
      </div>
    )

  const workspace = wsQuery.data
  const modeLabel = t(`mode.${workspace.mode}` as TKey)
  const groups = navFor(workspace.mode, workspace.role)

  return (
    <div className="min-h-screen md:grid md:grid-cols-[17rem_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:bg-surface focus:p-2">
        {t('nav.skip')}
      </a>
      <aside className={`${open ? 'block' : 'hidden'} border-r border-line bg-surface md:block`} aria-label={t('nav.primary')}>
        <div className="space-y-3 border-b border-line p-4">
          <Link to="/" className="text-lg font-semibold tracking-tight text-moss">GreenGuardian</Link>
          <div>
            <label htmlFor="ws-switch" className="sr-only">{t('nav.switchWorkspace')}</label>
            <select
              id="ws-switch"
              value={ws}
              onChange={(e) => (e.target.value === '__new' ? navigate('/') : navigate(`/w/${e.target.value}`))}
              className="w-full rounded border border-line bg-canvas px-2 py-1.5 text-sm"
            >
              {(all.data ?? [workspace]).map((w) => (
                <option key={w.id} value={w.id}>{w.name}</option>
              ))}
              <option value="__new">{t('nav.allWorkspaces')}</option>
            </select>
            <p className="mt-1 text-xs text-ink-3">{modeLabel} · {te('role', workspace.role)}</p>
          </div>
        </div>
        <nav className="max-h-[calc(100vh-9rem)] overflow-y-auto p-2 text-sm">
          {groups.map((g) => (
            <div key={g.group} className="mb-3">
              {g.group !== 'Home' && <p className="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-ink-3">{t(`nav.group.${g.group}` as TKey)}</p>}
              <ul>
                {g.items.map((r) => {
                  const label = statusLabel(r)
                  return (
                    <li key={r.path || 'home'}>
                      <NavLink
                        to={pathFor(ws, r)}
                        end={r.path === ''}
                        onClick={() => setOpen(false)}
                        className={({ isActive }) =>
                          `flex items-center justify-between gap-2 rounded px-2 py-1.5 ${isActive ? 'bg-surface-2 font-medium text-ink' : r.status === 'live' ? 'text-ink hover:bg-surface-2' : 'text-ink-3 hover:bg-surface-2'}`
                        }
                      >
                        <span>{t(routeKey(r))}</span>
                        {label && <span className="text-[10px] uppercase tracking-wide text-ink-3">{r.status === 'soon' && r.stage !== 'mvp' ? t('nav.status.soonShort') : t('nav.status.devShort')}</span>}
                      </NavLink>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </nav>
      </aside>
      <div className="min-w-0">
        <header className="flex items-center justify-between gap-3 border-b border-line bg-surface px-4 py-2">
          <button type="button" className="rounded border border-line px-2 py-1 text-sm md:hidden" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
            {t('nav.menu')}
          </button>
          <div className="min-w-0 truncate text-sm">
            <span className="font-medium">{workspace.name}</span>
            <span className="ml-2 hidden sm:inline"><StatusChip tone="neutral">{modeLabel}</StatusChip></span>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="hidden text-ink-2 sm:inline">{user?.name}</span>
            <LanguageSwitcher />
            <TourButton ws={ws} mode={workspace.mode} role={workspace.role} />
            <button type="button" onClick={() => logout().then(() => navigate('/login'))} className="rounded border border-line px-2 py-1 hover:bg-surface-2">
              {t('nav.signOut')}
            </button>
          </div>
        </header>
        <main id="main" className="mx-auto max-w-5xl p-4 md:p-6">
          <Outlet context={{ ws, workspace, capabilities: caps.data } satisfies WorkspaceCtx} />
        </main>
      </div>
    </div>
  )
}
