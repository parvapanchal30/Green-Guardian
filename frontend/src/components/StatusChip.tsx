import type { ReactNode } from 'react'

export type Tone = 'healthy' | 'at-risk' | 'critical' | 'soon' | 'building' | 'live' | 'neutral' | 'info'

// Field Ledger chips (ADR-069): a soft fill for status, an outline for neutral and planned states.
const STYLES: Record<Tone, string> = {
  healthy: 'bg-healthy-soft text-healthy border-transparent',
  'at-risk': 'bg-at-risk-soft text-at-risk border-transparent',
  critical: 'bg-critical-soft text-critical border-transparent',
  soon: 'text-soon border-soon border-dashed',
  building: 'text-ink-2 border-ink-3 border-dashed',
  live: 'bg-healthy-soft text-healthy border-transparent',
  neutral: 'bg-surface text-ink-2 border-line',
  info: 'bg-info-soft text-info border-transparent',
}

// Status is never colour-only: every tone has a distinct glyph and always carries text.
const GLYPH: Record<Tone, string> = {
  healthy: '●',
  'at-risk': '▲',
  critical: '■',
  soon: '◌',
  building: '◐',
  live: '●',
  neutral: '○',
  info: '◆',
}

export function StatusChip({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-[3px] border px-2 py-px text-xs font-semibold whitespace-nowrap ${STYLES[tone]}`}
    >
      <span aria-hidden="true" className="text-[0.7em]">{GLYPH[tone]}</span>
      {children}
    </span>
  )
}
