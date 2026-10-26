import type { ReactNode } from 'react'
import { ProblemError } from '../api/client'
import { useT } from '../i18n'
import { Icon, type IconName } from './icons'

export function Skeleton({ className = 'h-4 w-full' }: { className?: string }) {
  return <div aria-hidden="true" className={`animate-pulse rounded bg-surface-2 ${className}`} />
}

export function LoadingBlock({ label }: { label?: string }) {
  const t = useT()
  return (
    <div role="status" aria-live="polite" className="space-y-3 py-2">
      <span className="sr-only">{label ?? t('common.loading')}…</span>
      <Skeleton className="h-5 w-1/3" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-5/6" />
    </div>
  )
}

export function EmptyState({ title, children, action, icon }: { title: string; children?: ReactNode; action?: ReactNode; icon?: IconName }) {
  return (
    <div className="rounded-lg border-[1.5px] border-dashed border-line bg-surface p-6 text-center">
      {icon && <Icon name={icon} size={30} className="mx-auto mb-2 text-moss" />}
      <p className="font-display text-lg font-semibold text-ink">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-prose text-sm text-ink-2">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

/** "5 minutes", "1 minute", "30 seconds" (rounded up so the person never retries too early). */
export function waitText(seconds: number): string {
  if (seconds < 60) {
    const n = Math.max(1, Math.ceil(seconds))
    return `${n} second${n === 1 ? '' : 's'}`
  }
  const m = Math.ceil(seconds / 60)
  return `${m} minute${m === 1 ? '' : 's'}`
}

export function errorMessage(e: unknown): string {
  if (e instanceof ProblemError) {
    if (e.status === 429) return `Too many attempts. Please wait ${e.retryAfterS ? waitText(e.retryAfterS) : 'a little while'} and try again.`
    // Server-side failures carry a reference the person can quote; it matches the logs and the audit trail.
    if (e.status >= 500 && e.requestId) return `${e.message} (reference ${e.requestId})`
    return e.message
  }
  return e instanceof Error ? e.message : 'Something went wrong'
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const t = useT()
  const forbidden = error instanceof ProblemError && error.status === 403
  return (
    <div role="alert" className="rounded-lg border border-critical bg-surface p-4">
      <p className="font-medium text-critical">{forbidden ? t('state.noAccess') : t('state.loadFailed')}</p>
      <p className="mt-1 text-sm text-ink-2">{errorMessage(error)}</p>
      {onRetry && !forbidden && (
        <button type="button" onClick={onRetry} className="mt-3 rounded border border-line px-3 py-1.5 text-sm hover:bg-surface-2">
          {t('state.tryAgain')}
        </button>
      )}
    </div>
  )
}
