import { useEffect, useId, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { Role, WorkspaceMode } from '../../api/types'
import { useI18n } from '../../i18n'
import { useAuth } from '../../lib/auth'
import { readTheme, saveTheme, type ThemePref } from '../../lib/theme'
import { Icon } from '../icons'
import { LanguageSwitcher } from '../LanguageSwitcher'
import { TourButton } from '../TourPanel'
import { Segmented } from '../ui'

function initials(name: string | undefined): string {
  const words = (name ?? '').replace(/\(.*?\)/g, '').trim().split(/\s+/).filter(Boolean)
  return (words.length > 1 ? words[0][0] + words[1][0] : (words[0] ?? '?').slice(0, 2)).toUpperCase()
}

/**
 * The person's own menu: who is signed in and in which role, language, light or dark, the tour, all workspaces and
 * sign out. A disclosure (button + panel): Esc or a click outside closes it.
 */
export function AccountMenu({ ws, mode, role }: { ws: string; mode: WorkspaceMode; role: Role }) {
  const { t, te } = useI18n()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [theme, setTheme] = useState<ThemePref>(() => readTheme())
  const ref = useRef<HTMLDivElement>(null)
  const panelId = useId()

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false)
    window.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDown)
    }
  }, [open])

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={t('navx.account', { name: user?.name ?? '', role: te('role', role) })}
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-md px-1.5 py-1 hover:bg-surface-2"
      >
        <span aria-hidden="true" className="flex h-8 w-8 items-center justify-center rounded-full bg-soil text-[13px] font-semibold text-white">{initials(user?.name)}</span>
        <span className="hidden flex-col text-left leading-tight sm:flex" aria-hidden="true">
          <span className="text-sm font-semibold">{user?.name}</span>
          <span className="text-xs text-ink-2">{te('role', role)}</span>
        </span>
        <Icon name="expand" size={16} className="hidden sm:block" />
      </button>
      {open && (
        <div id={panelId} className="absolute top-full right-0 z-40 mt-1 w-72 rounded-lg border border-line bg-surface p-3 text-sm shadow-lg">
          <p className="font-semibold">{user?.name}</p>
          <p className="mb-3 text-xs text-ink-2">{user?.email} · {te('role', role)}</p>
          <div className="space-y-3 border-t border-line-soft pt-3">
            <label className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-2"><Icon name="language" size={16} />{t('lang.label')}</span>
              <LanguageSwitcher />
            </label>
            <div className="flex flex-col gap-1.5">
              <span className="text-ink-2">{t('navx.theme')}</span>
              <Segmented
                label={t('navx.theme')}
                value={theme}
                onChange={(v) => {
                  setTheme(v)
                  saveTheme(v)
                }}
                options={[
                  { value: 'system', label: t('navx.theme.system') },
                  { value: 'light', label: t('navx.theme.light') },
                  { value: 'dark', label: t('navx.theme.dark') },
                ]}
              />
            </div>
          </div>
          <div className="mt-3 flex flex-col gap-1 border-t border-line-soft pt-3">
            <TourButton ws={ws} mode={mode} role={role} />
            <Link to="/" onClick={() => setOpen(false)} className="rounded-md px-2 py-1.5 hover:bg-surface-2">{t('nav.allWorkspaces')}</Link>
            <button type="button" onClick={() => logout().then(() => navigate('/login'))} className="flex items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-surface-2">
              <Icon name="signOut" size={16} />
              {t('nav.signOut')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
