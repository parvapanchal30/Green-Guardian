import type { Role } from '../api/types'

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

/** "3 days ago" / "in 2 days". Pure given `now`, so it is testable. */
export function relative(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return 'never'
  const diff = new Date(iso).getTime() - now.getTime()
  if (Number.isNaN(diff)) return '—'
  const abs = Math.abs(diff)
  const mins = Math.round(abs / 60_000)
  const hours = Math.round(abs / 3_600_000)
  const days = Math.round(abs / 86_400_000)
  const unit = abs < 3_600_000 ? [mins, 'min'] : abs < 86_400_000 ? [hours, 'h'] : [days, days === 1 ? 'day' : 'days']
  if (abs < 60_000) return 'just now'
  return diff < 0 ? `${unit[0]} ${unit[1]} ago` : `in ${unit[0]} ${unit[1]}`
}

export const label = (s: string): string => s.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())

const RANK: Record<Role, number> = { viewer: 0, worker: 1, manager: 2, admin: 3, owner: 4 }
/** Mirrors the server's role ladder; the server remains the authority (this only hides buttons that would 403). */
export const atLeast = (role: Role, minimum: Role): boolean => RANK[role] >= RANK[minimum]

export function toIsoOrUndefined(localDateTime: string): string | undefined {
  if (!localDateTime) return undefined
  const d = new Date(localDateTime)
  return Number.isNaN(d.getTime()) ? undefined : d.toISOString()
}
