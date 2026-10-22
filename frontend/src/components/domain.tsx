import type { ReactNode } from 'react'
import type { HealthBand, Method, Severity, TaskStatus } from '../api/types'
import { useI18n } from '../i18n'
import { StatusChip, type Tone } from './StatusChip'

export function HealthChip({ band, score }: { band: HealthBand | null; score?: number | null }) {
  const { t, te } = useI18n()
  if (!band) return <StatusChip tone="neutral">{t('health.none')}</StatusChip>
  const tone: Tone = band === 'healthy' ? 'healthy' : band === 'at_risk' ? 'at-risk' : 'critical'
  return (
    <StatusChip tone={tone}>
      {te('health', band)}
      {score != null ? ` · ${Math.round(score)}` : ''}
    </StatusChip>
  )
}

const SEV_TONE: Record<Severity, Tone> = { low: 'neutral', medium: 'at-risk', high: 'critical', critical: 'critical' }
export function SeverityChip({ severity }: { severity: Severity }) {
  const { te } = useI18n()
  return <StatusChip tone={SEV_TONE[severity]}>{te('severity', severity)}</StatusChip>
}

/** Always shows what produced an output. A rule is never presented as AI. */
export function MethodBadge({ method }: { method: Method }) {
  const { te } = useI18n()
  return <StatusChip tone="neutral">{te('method', method)}</StatusChip>
}

export function StateChip({ state, open = true }: { state: string; open?: boolean }) {
  const { te } = useI18n()
  return <StatusChip tone={open ? 'building' : 'live'}>{te('issueState', state)}</StatusChip>
}

const TASK_TONE: Record<TaskStatus, Tone> = { todo: 'neutral', in_progress: 'building', blocked: 'at-risk', done: 'live', cancelled: 'soon' }
export function TaskStatusChip({ status, overdue }: { status: TaskStatus; overdue?: boolean }) {
  const { t, te } = useI18n()
  return (
    <span className="inline-flex items-center gap-1">
      <StatusChip tone={TASK_TONE[status]}>{te('taskStatus', status)}</StatusChip>
      {overdue && <StatusChip tone="critical">{t('chip.overdue')}</StatusChip>}
    </span>
  )
}

export function PageHeader({ title, children, subtitle }: { title: string; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <div className="mt-1 text-sm text-ink-2">{subtitle}</div>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </header>
  )
}

export const btn = 'rounded border border-line px-3 py-1.5 text-sm hover:bg-surface-2 disabled:opacity-50'
export const btnPrimary = 'rounded bg-moss px-3 py-1.5 text-sm text-moss-ink hover:opacity-90 disabled:opacity-50'
export const input = 'w-full rounded border border-line bg-canvas px-2 py-1.5 text-sm'

export function Field({ id, label: text, hint, children }: { id: string; label: string; hint?: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm text-ink-2">
        {text}
      </label>
      {children}
      {hint && <p className="mt-1 text-xs text-ink-3">{hint}</p>}
    </div>
  )
}

export function Pagination({ total, limit, offset, onChange }: { total: number; limit: number; offset: number; onChange: (offset: number) => void }) {
  if (total <= limit) return null
  const from = offset + 1
  const to = Math.min(offset + limit, total)
  return <PaginationNav from={from} to={to} total={total} limit={limit} offset={offset} onChange={onChange} />
}

function PaginationNav({ from, to, total, limit, offset, onChange }: { from: number; to: number; total: number; limit: number; offset: number; onChange: (offset: number) => void }) {
  const { t } = useI18n()
  return (
    <nav aria-label={t('common.pagination')} className="mt-3 flex items-center justify-between text-sm text-ink-2">
      <span>
        {t('common.range', { from, to, total })}
      </span>
      <span className="flex gap-2">
        <button type="button" className={btn} disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          {t('common.previous')}
        </button>
        <button type="button" className={btn} disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
          {t('common.next')}
        </button>
      </span>
    </nav>
  )
}
