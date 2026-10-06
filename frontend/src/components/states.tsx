import type { ReactNode } from 'react'
import { ProblemError } from '../api/client'

export function Skeleton({ className = 'h-4 w-full' }: { className?: string }) {
  return <div aria-hidden="true" className={`animate-pulse rounded bg-surface-2 ${className}`} />
}

export function LoadingBlock({ label = 'Loading' }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="space-y-3 py-2">
      <span className="sr-only">{label}…</span>
      <Skeleton className="h-5 w-1/3" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-5/6" />
    </div>
  )
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line bg-surface p-6 text-center">
      <p className="font-medium text-ink">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-prose text-sm text-ink-2">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function errorMessage(e: unknown): string {
  if (e instanceof ProblemError) return e.message
  return e instanceof Error ? e.message : 'Something went wrong'
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const forbidden = error instanceof ProblemError && error.status === 403
  return (
    <div role="alert" className="rounded-lg border border-critical bg-surface p-4">
      <p className="font-medium text-critical">{forbidden ? 'You do not have access to this' : 'Could not load this'}</p>
      <p className="mt-1 text-sm text-ink-2">{errorMessage(error)}</p>
      {onRetry && !forbidden && (
        <button type="button" onClick={onRetry} className="mt-3 rounded border border-line px-3 py-1.5 text-sm hover:bg-surface-2">
          Try again
        </button>
      )}
    </div>
  )
}
