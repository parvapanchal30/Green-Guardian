import { useEffect, useState } from 'react'
import { Link, Navigate, Outlet, useLocation, useNavigate, useOutletContext, useParams } from 'react-router-dom'
import type { Capability, Dashboard, Workspace } from '../api/types'
import { Icon } from '../components/icons'
import { AccountMenu } from '../components/shell/AccountMenu'
import { BottomBar } from '../components/shell/BottomBar'
import { SearchBox } from '../components/shell/SearchBox'
import { SectionTabs } from '../components/shell/SectionTabs'
import { ErrorState, LoadingBlock } from '../components/states'
import { useI18n, type TKey } from '../i18n'
import { useAuth } from '../lib/auth'
import { useCapabilities, useWorkspace, useWorkspaces } from '../lib/queries'
import { useDashboard } from '../lib/slice'
import { activeItemId, menuFor, sectionTabs, type NavBadge, type NavItem } from './routes'

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

function badgeCount(badge: NavBadge | undefined, d: Dashboard | undefined): number | null {
  if (!badge || !d) return null
  const n = badge === 'tasks' ? d.work.open_tasks : badge === 'issues' ? d.work.open_issues : d.work.open_recommendations
  return n > 0 ? n : null
}

function MenuLink({ ws, item, active, count, onPick }: { ws: string; item: NavItem; active: boolean; count: number | null; onPick: () => void }) {
  const { t } = useI18n()
  return (
    <Link
      to={`/w/${ws}${item.path ? `/${item.path}` : ''}`}
      aria-current={active ? 'page' : undefined}
      onClick={onPick}
      className={`flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm ${active ? 'bg-moss-soft font-semibold text-ink' : 'text-ink hover:bg-surface-2'}`}
    >
      <Icon name={item.icon} size={18} className={active ? 'text-moss' : 'text-ink-2'} />
      <span className="flex-1">{t(item.label)}</span>
      {count != null && <span className="font-mono text-xs text-ink-2">{count}</span>}
    </Link>
  )
}

export function WorkspaceLayout() {
  const { t, te } = useI18n()
  const { ws = '' } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const wsQuery = useWorkspace(ws)
  const caps = useCapabilities(ws)
  const all = useWorkspaces()
  const dash = useDashboard(ws)
  const [open, setOpen] = useState(false)
  const [searching, setSearching] = useState(false)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  if (wsQuery.isLoading) return <div className="p-8"><LoadingBlock label={t('nav.switchWorkspace')} /></div>
  if (wsQuery.error || !wsQuery.data)
    return (
      <div className="mx-auto max-w-xl space-y-4 p-8">
        <ErrorState error={wsQuery.error ?? new Error(t('common.workspaceNotFound'))} onRetry={() => wsQuery.refetch()} />
        <Link to="/" className="text-moss underline">{t('nav.backToWorkspaces')}</Link>
      </div>
    )

  const workspace = wsQuery.data
  const modeLabel = t(`mode.${workspace.mode}` as TKey)
  const { sections, footer } = menuFor(workspace.mode, workspace.role)
  const rel = location.pathname.replace(new RegExp(`^/w/${ws}/?`), '').replace(/\/$/, '')
  const activeId = activeItemId(rel, [...sections.flatMap((s) => s.items), ...footer])
  const tabs = sectionTabs(rel, workspace.mode, workspace.role)
  const close = () => setOpen(false)

  return (
    <div className="min-h-screen md:grid md:grid-cols-[15rem_1fr] print:block">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:bg-surface focus:p-2">
        {t('nav.skip')}
      </a>
      {open && <div className="fixed inset-0 z-30 bg-ink/40 md:hidden" aria-hidden="true" onClick={close} />}
      <aside
        aria-label={t('nav.primary')}
        className={`${open ? 'fixed inset-y-0 left-0 z-40 flex w-72 shadow-xl' : 'hidden'} flex-col border-r border-line bg-surface md:sticky md:top-0 md:flex md:h-screen md:w-auto md:shadow-none print:hidden`}
      >
        <div className="flex flex-col gap-3 px-3 pt-5 pb-3">
          <Link to="/" className="flex items-center gap-2.5 px-1.5">
            <span className="flex h-[30px] w-[30px] items-center justify-center rounded-md bg-moss text-moss-ink"><Icon name="comingNext" size={17} /></span>
            <span className="font-display text-[19px] font-bold text-ink">GreenGuardian</span>
          </Link>
          <div>
            <label htmlFor="ws-switch" className="sr-only">{t('nav.switchWorkspace')}</label>
            <select
              id="ws-switch"
              value={ws}
              onChange={(e) => (e.target.value === '__new' ? navigate('/') : navigate(`/w/${e.target.value}`))}
              className="w-full rounded-md border border-line bg-canvas px-2.5 py-2 text-sm font-semibold"
            >
              {(all.data ?? [workspace]).map((w) => (
                <option key={w.id} value={w.id}>{w.name}</option>
              ))}
              <option value="__new">{t('nav.allWorkspaces')}</option>
            </select>
            <p className="mt-1 px-1 text-xs text-ink-2">{modeLabel} · {te('role', workspace.role)}</p>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto px-3 pb-3">
          {sections.map((s) => (
            <div key={s.id} className="mb-3">
              {s.label && <p className="px-2.5 pb-1 font-mono text-[10.5px] tracking-[0.08em] text-soil uppercase">{t(s.label)}</p>}
              <ul className="flex flex-col gap-px">
                {s.items.map((item) => (
                  <li key={item.id}>
                    <MenuLink ws={ws} item={item} active={item.id === activeId} count={badgeCount(item.badge, dash.data)} onPick={close} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <ul className="flex flex-col gap-px border-t border-line-soft px-3 py-3">
          {footer.map((item) => (
            <li key={item.id}>
              <MenuLink ws={ws} item={item} active={item.id === activeId} count={null} onPick={close} />
            </li>
          ))}
        </ul>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex h-[58px] items-center gap-3 border-b border-line bg-surface px-4 md:px-8 print:hidden">
          <span className="min-w-0 truncate font-semibold md:hidden">{workspace.name}</span>
          <div className="hidden flex-1 md:block">
            <SearchBox ws={ws} />
          </div>
          <button
            type="button"
            onClick={() => setSearching((v) => !v)}
            aria-expanded={searching}
            aria-label={t('navx.search.label')}
            className="ml-auto flex h-11 w-11 items-center justify-center rounded-md hover:bg-surface-2 md:hidden"
          >
            <Icon name="search" size={20} />
          </button>
          <div className="md:ml-auto">
            <AccountMenu ws={ws} mode={workspace.mode} role={workspace.role} />
          </div>
        </header>
        {searching && (
          <div className="border-b border-line bg-surface px-4 py-2 md:hidden">
            <SearchBox ws={ws} autoFocus onDone={() => setSearching(false)} />
          </div>
        )}
        <main id="main" className="mx-auto max-w-6xl px-4 pt-5 pb-28 md:px-8 md:pt-7 md:pb-10">
          {tabs && <SectionTabs ws={ws} tabs={tabs} />}
          <Outlet context={{ ws, workspace, capabilities: caps.data } satisfies WorkspaceCtx} />
        </main>
      </div>
      <BottomBar ws={ws} moreOpen={open} onMore={() => setOpen((v) => !v)} onNavigate={close} />
    </div>
  )
}
