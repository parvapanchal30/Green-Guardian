import { NavLink } from 'react-router-dom'
import { pathFor, routeKey, type NavRoute } from '../../app/routes'
import { useI18n } from '../../i18n'

/** Sibling pages of one menu entry (Trees, Plants and Batches under Assets; Growth beside Health; …) as links. */
export function SectionTabs({ ws, tabs }: { ws: string; tabs: NavRoute[] }) {
  const { t } = useI18n()
  return (
    <nav aria-label={t('navx.sectionTabs')} className="mb-5 flex gap-6 overflow-x-auto border-b border-line print:hidden">
      {tabs.map((r) => (
        <NavLink
          key={r.path}
          to={pathFor(ws, r)}
          end
          className={({ isActive }) =>
            `-mb-px border-b-2 py-2.5 text-[15px] whitespace-nowrap ${isActive ? 'border-moss font-semibold text-ink' : 'border-transparent text-ink-2 hover:text-ink'}`
          }
        >
          {t(routeKey(r))}
          {r.status === 'soon' && <span className="ml-1.5 font-mono text-[10px] text-ink-3 uppercase">{t('nav.status.soonShort')}</span>}
        </NavLink>
      ))}
    </nav>
  )
}
