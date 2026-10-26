import { useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Task } from '../../api/types'
import { useI18n } from '../../i18n'
import { useWorkspaceSearch } from '../../lib/search'
import { Icon } from '../icons'

/**
 * The search field in the top bar: plants by name or tag, issues and tasks by title or key (GG-001, T-004).
 * Ctrl+K (or Cmd+K) puts the cursor in it; Esc closes the results.
 */
export function SearchBox({ ws, autoFocus = false, onDone }: { ws: string; autoFocus?: boolean; onDone?: () => void }) {
  const { t } = useI18n()
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)
  const resultsId = useId()
  const r = useWorkspaceSearch(ws, text)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [])

  const done = () => {
    setOpen(false)
    setText('')
    onDone?.()
  }
  const total = r.assets.length + r.issues.length + r.tasks.length
  const show = open && text.trim().length > 0

  return (
    <div ref={boxRef} className="relative w-full max-w-[500px]">
      <label className="flex items-center gap-2.5 rounded-md border border-line bg-canvas px-3 py-1.5 text-sm text-ink-2 focus-within:border-moss">
        <Icon name="search" size={16} />
        <input
          ref={inputRef}
          type="search"
          aria-label={t('navx.search.label')}
          value={text}
          autoFocus={autoFocus}
          onChange={(e) => {
            setText(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key !== 'Escape') return
            setOpen(false)
            onDone?.()
          }}
          placeholder={t('navx.search.placeholder')}
          aria-controls={show ? resultsId : undefined}
          className="min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-ink-3"
        />
        <kbd aria-hidden="true" className="hidden rounded border border-line bg-surface px-1.5 font-mono text-[11px] text-ink-2 sm:inline">Ctrl K</kbd>
      </label>
      {show && (
        <div id={resultsId} role="region" aria-label={t('navx.search.results')} aria-live="polite" className="absolute top-full right-0 left-0 z-40 mt-1 max-h-[70vh] overflow-y-auto rounded-lg border border-line bg-surface p-2 shadow-lg">
          {!r.on && <p className="px-2 py-1.5 text-sm text-ink-2">{t('navx.search.hint')}</p>}
          {r.on && r.loading && total === 0 && <p className="px-2 py-1.5 text-sm text-ink-2">{t('navx.search.loading')}</p>}
          {r.on && !r.loading && total === 0 && <p className="px-2 py-1.5 text-sm text-ink-2">{t('navx.search.none', { q: r.q })}</p>}
          <ResultGroup title={t('navx.search.plants')} icon="assets" items={r.assets.map((a) => ({ id: a.id, to: `/w/${ws}/assets/${a.id}`, key: a.tag_code, text: a.label, sub: [a.species_name, a.location_name].filter(Boolean).join(' · ') }))} onPick={done} />
          <ResultGroup title={t('navx.search.issues')} icon="issues" items={r.issues.map((i) => ({ id: i.id, to: `/w/${ws}/issues/${i.id}`, key: i.key, text: i.title }))} onPick={done} />
          <ResultGroup title={t('navx.search.tasks')} icon="tasks" items={r.tasks.map((x) => ({ id: x.id, to: taskTarget(ws, x), key: x.key, text: x.title, sub: x.asset_label ?? undefined }))} onPick={done} />
        </div>
      )}
    </div>
  )
}

/** Tasks have no page of their own: open the issue it belongs to, else its plant, else the task list. */
function taskTarget(ws: string, task: Task): string {
  if (task.issue_id) return `/w/${ws}/issues/${task.issue_id}`
  if (task.asset_id) return `/w/${ws}/assets/${task.asset_id}`
  return `/w/${ws}/tasks`
}

function ResultGroup({ title, icon, items, onPick }: { title: string; icon: 'assets' | 'issues' | 'tasks'; items: { id: string; to: string; key: string | null; text: string; sub?: string }[]; onPick: () => void }) {
  if (!items.length) return null
  return (
    <div className="mb-1">
      <p className="flex items-center gap-1.5 px-2 pt-1 pb-0.5 font-mono text-[10.5px] tracking-[0.08em] text-soil uppercase">
        <Icon name={icon} size={13} />
        {title}
      </p>
      <ul>
        {items.map((it) => (
          <li key={it.id}>
            <Link to={it.to} onClick={onPick} className="flex items-baseline gap-2.5 rounded-md px-2 py-1.5 text-sm text-ink hover:bg-surface-2">
              {it.key && <span className="font-mono text-xs text-ink-2">{it.key}</span>}
              <span className="min-w-0 flex-1 truncate">{it.text}</span>
              {it.sub && <span className="truncate text-xs text-ink-3">{it.sub}</span>}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
