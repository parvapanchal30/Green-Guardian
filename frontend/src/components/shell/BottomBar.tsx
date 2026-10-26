import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useI18n } from '../../i18n'
import { Icon } from '../icons'
import { RecordPicker } from './RecordPicker'

/**
 * The phone navigation (below the md breakpoint): Today, Map, Record, Tasks, More. Every entry keeps its label
 * (idea 8 was redrawn with labels kept for new users); targets are at least 44 px. More opens the full menu.
 */
export function BottomBar({ ws, onMore, moreOpen, onNavigate }: { ws: string; onMore: () => void; moreOpen: boolean; onNavigate?: () => void }) {
  const { t } = useI18n()
  const [picking, setPicking] = useState(false)
  const item = (active: boolean) => `flex min-h-11 w-16 flex-col items-center justify-end gap-0.5 pt-1.5 text-[11.5px] ${active ? 'font-semibold text-moss' : 'text-ink-2'}`
  return (
    <>
      <nav aria-label={t('navx.phoneNav')} className="fixed inset-x-0 bottom-0 z-30 flex items-end justify-around border-t border-line bg-surface px-2 pt-1 pb-[max(10px,env(safe-area-inset-bottom))] md:hidden print:hidden">
        <NavLink to={`/w/${ws}`} end onClick={onNavigate} className={({ isActive }) => item(isActive)}>
          <Icon name="today" size={22} />
          {t('navx.today')}
        </NavLink>
        <NavLink to={`/w/${ws}/monitor/map`} onClick={onNavigate} className={({ isActive }) => item(isActive)}>
          <Icon name="map" size={22} />
          {t('nav.route.monitor.map')}
        </NavLink>
        <button type="button" onClick={() => {
            onNavigate?.()
            setPicking(true)
          }} aria-haspopup="dialog" className="flex w-16 flex-col items-center gap-1 text-[11.5px] font-semibold text-ink">
          <span className="-mt-6 flex h-[52px] w-[52px] items-center justify-center rounded-full border-4 border-canvas bg-moss text-moss-ink">
            <Icon name="record" size={24} />
          </span>
          {t('navx.record')}
        </button>
        <NavLink to={`/w/${ws}/tasks`} onClick={onNavigate} className={({ isActive }) => item(isActive)}>
          <Icon name="tasks" size={22} />
          {t('nav.route.tasks')}
        </NavLink>
        <button type="button" onClick={onMore} aria-expanded={moreOpen} className={item(moreOpen)}>
          <Icon name="menu" size={22} />
          {t('navx.more')}
        </button>
      </nav>
      {picking && <RecordPicker ws={ws} onClose={() => setPicking(false)} />}
    </>
  )
}
