import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useI18n } from '../../i18n'
import { SEARCH_MIN, useWorkspaceSearch } from '../../lib/search'
import { Icon } from '../icons'

/**
 * "Record" from anywhere on a phone: find the plant, then record on its page (the observation form, #record).
 * A modal dialog: focus starts in the search field, Esc or Close ends it.
 */
export function RecordPicker({ ws, onClose }: { ws: string; onClose: () => void }) {
  const { t } = useI18n()
  const [text, setText] = useState('')
  const r = useWorkspaceSearch(ws, text, ['assets'])
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-end bg-ink/45 sm:items-center sm:justify-center" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-labelledby="record-pick-title" className="w-full rounded-t-2xl bg-surface p-4 pb-6 sm:max-w-md sm:rounded-xl">
        <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line sm:hidden" aria-hidden="true" />
        <div className="mb-3 flex items-center gap-2">
          <h2 id="record-pick-title" className="text-[22px] font-bold">{t('navx.recordPick.title')}</h2>
          <button type="button" onClick={onClose} aria-label={t('navx.close')} className="ml-auto flex h-11 w-11 items-center justify-center rounded-md hover:bg-surface-2">
            <Icon name="close" size={20} />
          </button>
        </div>
        <label className="flex items-center gap-2 rounded-md border-[1.5px] border-moss px-3 py-2.5">
          <Icon name="search" size={18} className="text-ink-2" />
          <span className="sr-only">{t('navx.recordPick.label')}</span>
          <input ref={inputRef} type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder={t('navx.recordPick.placeholder')} className="min-w-0 flex-1 bg-transparent outline-none" />
        </label>
        <div aria-live="polite" className="mt-2 max-h-[50vh] overflow-y-auto">
          {text.trim().length < SEARCH_MIN && <p className="px-1 py-2 text-sm text-ink-2">{t('navx.recordPick.body')}</p>}
          {r.on && !r.loading && r.assets.length === 0 && <p className="px-1 py-2 text-sm text-ink-2">{t('navx.search.none', { q: r.q })}</p>}
          <ul>
            {r.assets.map((a) => (
              <li key={a.id}>
                <Link to={`/w/${ws}/assets/${a.id}#record`} onClick={onClose} className="flex min-h-11 items-center gap-3 rounded-md px-2 py-2 hover:bg-surface-2">
                  {a.tag_code && <span className="font-mono text-xs text-ink-2">{a.tag_code}</span>}
                  <span className="flex-1">
                    <span className="block font-semibold">{a.label}</span>
                    <span className="block text-xs text-ink-3">{[a.species_name, a.location_name].filter(Boolean).join(' · ')}</span>
                  </span>
                  <Icon name="next" size={18} className="text-ink-3" />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
