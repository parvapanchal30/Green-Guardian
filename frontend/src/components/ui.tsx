import type { ReactNode } from 'react'
import { useI18n } from '../i18n'
import { Icon } from './icons'

/*
 * Field Ledger building blocks (ADR-069, docs/DESIGN_SYSTEM.md). Pages compose these instead of repeating class
 * strings, so a later visual change lands in one place.
 */

/** A record key or code in the monospaced face: GG-001, T-004, N-102. */
export function Tag({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'critical' | 'moss' }) {
  const cls =
    tone === 'critical'
      ? 'border-critical/40 bg-critical-soft text-critical'
      : tone === 'moss'
        ? 'border-moss/40 bg-moss-soft text-moss'
        : 'border-line bg-surface text-ink'
  return <span className={`inline-block rounded-[3px] border px-1.5 font-mono text-xs leading-5 whitespace-nowrap ${cls}`}>{children}</span>
}

/** A white card with the standard border. */
export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-lg border border-line bg-surface ${className}`}>{children}</div>
}

/** A section title in the display face, with optional actions or a note on the right. */
export function SectionHeading({ title, id, children }: { title: string; id?: string; children?: ReactNode }) {
  return (
    <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <h2 id={id} className="text-[19px] font-semibold">
        {title}
      </h2>
      {children && <div className="ml-auto flex flex-wrap items-center gap-2 text-sm">{children}</div>}
    </div>
  )
}

type StatTone = 'neutral' | 'critical' | 'at-risk' | 'healthy'
const STAT_VALUE: Record<StatTone, string> = {
  neutral: 'text-ink',
  critical: 'text-critical',
  'at-risk': 'text-at-risk',
  healthy: 'text-healthy',
}

/** One figure: a label, the value in the display face, and an optional note (its basis or what it needs). */
export function StatTile({ label, value, note, tone = 'neutral' }: { label: string; value: ReactNode; note?: ReactNode; tone?: StatTone }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-lg border border-line bg-surface px-4 py-3">
      <span className="text-[13px] text-ink-2">{label}</span>
      <span className={`font-display text-[28px] leading-tight font-bold ${STAT_VALUE[tone]}`}>{value}</span>
      {note && <span className="text-xs text-ink-3">{note}</span>}
    </div>
  )
}

export interface SegmentOption<T extends string> {
  value: T
  label: string
  count?: number
}

/** A row of mutually exclusive buttons (a view switch or a filter). Each button reports aria-pressed. */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: SegmentOption<T>[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex overflow-hidden rounded-md border border-line bg-surface text-sm">
      {options.map((o) => {
        const on = o.value === value
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(o.value)}
            className={`px-3 py-1.5 ${on ? 'bg-moss-soft font-semibold text-ink' : 'text-ink hover:bg-surface-2'}`}
          >
            {o.label}
            {o.count != null && <span className="ml-1.5 font-mono text-xs text-ink-2">{o.count}</span>}
          </button>
        )
      })}
    </div>
  )
}

/** Holds a page's filters and view switches on one wrapping row. */
export function FilterBar({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <div role={label ? 'search' : undefined} aria-label={label} className="mb-4 flex flex-wrap items-center gap-2.5">
      {children}
    </div>
  )
}

/**
 * Living plants split by their latest health band: one bar plus counts. Shapes in the legend repeat the chip glyphs
 * so the bands are told apart without colour.
 */
export function HealthBar({ healthy, atRisk, critical, noData = 0 }: { healthy: number; atRisk: number; critical: number; noData?: number }) {
  const { te, t, fmt } = useI18n()
  const total = healthy + atRisk + critical + noData
  const parts: { key: string; n: number; color: string; glyph: string; label: string }[] = [
    { key: 'healthy', n: healthy, color: 'bg-healthy', glyph: '●', label: te('health', 'healthy') },
    { key: 'at_risk', n: atRisk, color: 'bg-at-risk', glyph: '▲', label: te('health', 'at_risk') },
    { key: 'critical', n: critical, color: 'bg-critical', glyph: '■', label: te('health', 'critical') },
    { key: 'none', n: noData, color: 'bg-line', glyph: '○', label: t('health.none') },
  ]
  const summary = parts.filter((p) => p.n > 0 || p.key !== 'none').map((p) => `${fmt.number(p.n)} ${p.label}`).join(', ')
  return (
    <div className="flex flex-col gap-2">
      <div role="img" aria-label={summary} className="flex h-2.5 gap-0.5 overflow-hidden rounded-full bg-surface-2">
        {total > 0 && parts.filter((p) => p.n > 0).map((p) => <span key={p.key} className={p.color} style={{ flexGrow: p.n }} />)}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[13px]" aria-hidden="true">
        {parts
          .filter((p) => p.n > 0 || p.key !== 'none')
          .map((p) => (
            <li key={p.key} className="inline-flex items-center gap-1.5">
              <span className={`text-[0.7em] ${p.key === 'healthy' ? 'text-healthy' : p.key === 'at_risk' ? 'text-at-risk' : p.key === 'critical' ? 'text-critical' : 'text-ink-3'}`}>{p.glyph}</span>
              <b className="font-semibold">{fmt.number(p.n)}</b> {p.label}
            </li>
          ))}
      </ul>
    </div>
  )
}

export interface LedgerColumn<T> {
  key: string
  header: string
  cell: (row: T) => ReactNode
  /** The row's name. On phones it heads the card, across its width, without a label. */
  primary?: boolean
  /** Counts and dates: right-aligned in the table. */
  numeric?: boolean
}

/**
 * The one list pattern (ADR-073): a ledger table with monospaced column headers on wider screens; on phones every
 * row becomes a card, its name on top and the other cells as labelled pairs. One table in the page, restyled by
 * width, so the content and the accessible table are the same on every screen.
 */
export function LedgerTable<T>({ caption, columns, rows, rowKey }: { caption: string; columns: LedgerColumn<T>[]; rows: T[]; rowKey: (row: T) => string }) {
  return (
    <div className="relative md:overflow-x-auto md:rounded-lg md:border md:border-line md:bg-surface">
      <table className="block w-full text-left text-sm md:table">
        <caption className="sr-only">{caption}</caption>
        <thead className="sr-only border-b border-line bg-surface-2/60 md:not-sr-only md:table-header-group">
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className={`px-3 py-2 font-mono text-[11px] font-medium tracking-wide text-ink-2 uppercase whitespace-nowrap ${c.numeric ? 'text-right' : ''}`}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="flex flex-col gap-2 md:table-row-group">
          {rows.map((r) => (
            <tr key={rowKey(r)} className="grid grid-cols-2 gap-x-3 gap-y-2 rounded-lg border border-line bg-surface p-3 md:table-row md:rounded-none md:border-0 md:border-b md:border-line-soft md:p-0 md:last:border-0 md:hover:bg-surface-2/40">
              {columns.map((c) => (
                <td
                  key={c.key}
                  data-label={c.primary ? undefined : c.header}
                  className={`min-w-0 md:table-cell md:px-3 md:py-2.5 md:align-middle ${
                    c.primary
                      ? 'col-span-2'
                      : 'before:mb-0.5 before:block before:font-mono before:text-[11px] before:text-ink-3 before:uppercase before:content-[attr(data-label)] md:before:content-none'
                  } ${c.numeric ? 'tabular-nums md:text-right' : ''}`}
                >
                  {c.cell(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** A search field with its icon; the label is for screen readers, the placeholder says what it searches. */
export function SearchField({ id, label, value, onChange, placeholder }: { id: string; label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <div className="relative w-full max-w-xs">
      <label className="sr-only" htmlFor={id}>{label}</label>
      <Icon name="search" size={16} className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-ink-3" />
      <input id={id} type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className="w-full rounded-md border border-line bg-surface py-1.5 pr-2.5 pl-8 text-sm" />
    </div>
  )
}

/** A native select styled as a filter, with a screen-reader label. */
export function FilterSelect({ id, label, value, onChange, children }: { id: string; label: string; value: string; onChange: (v: string) => void; children: ReactNode }) {
  return (
    <>
      <label className="sr-only" htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm">
        {children}
      </select>
    </>
  )
}
