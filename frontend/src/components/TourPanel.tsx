import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Role, WorkspaceMode } from '../api/types'
import { useT, type TKey } from '../i18n'
import { stepsFor } from '../tour/steps'
import { btn, btnPrimary } from './domain'

const FOCUS_ATTR = 'data-tour-focus'
const WAIT_MS = 6000

function clearFocus() {
  for (const el of document.querySelectorAll<HTMLElement>(`[${FOCUS_ATTR}]`)) {
    el.style.outline = ''
    el.style.outlineOffset = ''
    el.removeAttribute(FOCUS_ATTR)
  }
}

/** Resolve with the element once it exists (pages render after their data arrives), or null after a timeout. */
function waitFor(find: () => Element | null, timeoutMs = WAIT_MS): Promise<Element | null> {
  return new Promise((resolve) => {
    const started = Date.now()
    const tick = () => {
      const el = find()
      if (el) return resolve(el)
      if (Date.now() - started > timeoutMs) return resolve(null)
      window.setTimeout(tick, 120)
    }
    tick()
  })
}

/**
 * A guided walk through the product for the current workspace: Back and Next move between pages and highlight the part
 * being explained. It only navigates and highlights: it never saves or changes anything. Esc or Close ends it.
 */
export function TourButton({ ws, mode, role }: { ws: string; mode: WorkspaceMode; role: Role }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" className="rounded-md px-2 py-1.5 text-left hover:bg-surface-2" onClick={() => setOpen(true)} aria-haspopup="dialog">
        {t('nav.tour')}
      </button>
      {open && <TourPanel ws={ws} mode={mode} role={role} onClose={() => setOpen(false)} />}
    </>
  )
}

export function TourPanel({ ws, mode, role, onClose }: { ws: string; mode: WorkspaceMode; role: Role; onClose: () => void }) {
  const t = useT()
  const steps = useMemo(() => stepsFor(mode, role), [mode, role])
  const [index, setIndex] = useState(0)
  const [missing, setMissing] = useState(false)
  const navigate = useNavigate()
  const step = steps[index]

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      clearFocus()
    }
  }, [onClose])

  useEffect(() => {
    let cancelled = false
    setMissing(false)
    clearFocus()
    async function show() {
      navigate(`/w/${ws}${step.path}`)
      if (step.openFirstAsset) {
        const link = await waitFor(() => document.querySelector('table tbody a[href*="/assets/"]'))
        if (cancelled) return
        if (!link) return setMissing(true)
        navigate(link.getAttribute('href') as string)
      }
      if (!step.focus) return
      const target = await waitFor(() => document.querySelector(step.focus as string))
      if (cancelled) return
      if (!target) return setMissing(true)
      const el = target as HTMLElement
      el.setAttribute(FOCUS_ATTR, '1')
      el.style.outline = '3px solid #f59e0b'
      el.style.outlineOffset = '4px'
      el.scrollIntoView?.({ block: 'start', behavior: 'smooth' })
    }
    void show()
    return () => {
      cancelled = true
    }
  }, [index, step, ws, navigate])

  if (!step) return null
  const last = index === steps.length - 1
  return (
    <div
      role="dialog"
      aria-label={t('tour.dialog')}
      aria-live="polite"
      className="fixed bottom-4 right-4 z-50 w-[min(24rem,calc(100vw-2rem))] rounded-lg border border-line bg-surface p-4 shadow-lg"
    >
      <p className="text-xs text-ink-3">{t('tour.stepOf', { n: index + 1, total: steps.length })}</p>
      <h2 className="mt-1 font-semibold">{t(`tour.step.${step.id}.title` as TKey)}</h2>
      <p className="mt-1 text-sm text-ink-2">{t(`tour.step.${step.id}.caption` as TKey)}</p>
      {missing && (
        <p role="status" className="mt-2 text-sm text-ink-3">
          {t('tour.missing')}
        </p>
      )}
      <div className="mt-3 flex items-center justify-between gap-2">
        <button type="button" className="text-sm text-ink-3 underline" onClick={onClose}>{t('tour.close')}</button>
        <div className="flex gap-2">
          <button type="button" className={btn} disabled={index === 0} onClick={() => setIndex((i) => i - 1)}>{t('tour.back')}</button>
          {last ? (
            <button type="button" className={btnPrimary} onClick={onClose}>{t('tour.finish')}</button>
          ) : (
            <button type="button" className={btnPrimary} onClick={() => setIndex((i) => i + 1)}>{t('tour.next')}</button>
          )}
        </div>
      </div>
    </div>
  )
}
