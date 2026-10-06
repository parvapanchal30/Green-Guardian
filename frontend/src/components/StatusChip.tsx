import type { ReactNode } from 'react'

export type Tone = 'healthy' | 'at-risk' | 'critical' | 'soon' | 'building' | 'live' | 'neutral'

const STYLES: Record<Tone, string> = {
  healthy: 'text-healthy border-healthy',
  'at-risk': 'text-at-risk border-at-risk',
  critical: 'text-critical border-critical',
  soon: 'text-soon border-soon border-dashed',
  building: 'text-ink-2 border-ink-3 border-dashed',
  live: 'text-healthy border-healthy',
  neutral: 'text-ink-2 border-line',
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
}

export function StatusChip({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-xs font-medium whitespace-nowrap ${STYLES[tone]}`}
    >
      <span aria-hidden="true">{GLYPH[tone]}</span>
      {children}
    </span>
  )
}
