import type { DashboardActivity, Recommendation } from '../api/types'
import type { TKey } from '../i18n'

type T = (key: TKey, params?: Record<string, string | number>) => string
type Te = (group: string, value: string, fallback?: string) => string
type Num = (v: number, o?: Intl.NumberFormatOptions) => string

const n = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)
const s = (v: unknown): string | null => (typeof v === 'string' && v.length > 0 ? v : null)

/**
 * A suggestion's title and explanation in the reader's language (ADR-081), written from the numbers the rule stored in
 * its evidence. Returns null when those numbers are missing (suggestions made before ADR-081, or an unknown rule):
 * the caller then shows the server's English text, which says the same thing.
 */
export function recommendationText(rec: Recommendation, t: T, te: Te, num: Num): { title: string; explanation: string } | null {
  // The rule's own numbers are stored under evidence.inputs (next to the run's provenance).
  const stored = (rec.evidence ?? {}) as Record<string, unknown>
  const e = ((stored.inputs as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>
  const label = s(e.label)
  if (!label) return null
  const whole = (v: number) => num(v, { maximumFractionDigits: 0 })
  switch (rec.rule_key) {
    case 'critical_health': {
      const score = n(e.score)
      const threshold = n(e.threshold)
      if (score === null || threshold === null) return null
      return {
        title: t('recx.critical.title', { label, score: whole(score) }),
        explanation: t('recx.critical.why', { score: whole(score), threshold: num(threshold) }),
      }
    }
    case 'health_decline': {
      const [from, to, drop, days, obs] = [n(e.from_score), n(e.to_score), n(e.drop), n(e.window_days), n(e.observations)]
      if (from === null || to === null || drop === null || days === null || obs === null) return null
      return {
        title: t('recx.decline.title', { label, drop: whole(drop), days }),
        explanation: t('recx.decline.why', { from: whole(from), to: whole(to), count: obs }),
      }
    }
    case 'inspection_gap': {
      const limit = n(e.interval_days)
      const days = n(e.days_since)
      if (limit === null) return null
      if (days === null) return { title: t('recx.gap.neverTitle', { label }), explanation: t('recx.gap.neverWhy', { limit }) }
      const basis = s(e.basis) ?? 'observation'
      const last = s(e.last_attention_at)
      return {
        title: t('recx.gap.title', { label, days, limit }),
        explanation: t('recx.gap.why', { basis: te('recx.basis', basis.replace(/ /g, '_')), date: last ? last.slice(0, 10) : '—', days, limit }),
      }
    }
    case 'irrigation_defer': {
      const f = (e.forecast ?? {}) as Record<string, unknown>
      const th = (e.thresholds ?? {}) as Record<string, unknown>
      const task = s(((e.task ?? {}) as Record<string, unknown>).key)
      const [mm, pct, minMm, minPct] = [n(f.rain_next_24h_mm), n(f.max_rain_probability_pct), n(th.min_rain_mm), n(th.min_probability_pct)]
      if (!task || mm === null || pct === null || minMm === null || minPct === null) return null
      return {
        title: t('recx.rain.title', { label, task, mm: num(mm) }),
        explanation: t('recx.rain.why', { mm: num(mm), pct: num(pct), minMm: num(minMm), minPct: num(minPct), task }),
      }
    }
    default:
      return null
  }
}

/**
 * One activity line in the reader's language (ADR-081): what happened, from the parts the server sends with it. Older
 * servers without those parts fall back to the English title and detail.
 */
export function activityText(a: DashboardActivity, t: T, te: Te, num: Num): { title: string; detail: string | null } {
  if (a.subject == null) {
    const title = a.key && a.title.startsWith(a.key) ? a.title.slice(a.key.length).trim() : a.title
    return { title, detail: a.detail }
  }
  if (a.type === 'observation') {
    const bits = [
      a.health_score != null ? t('recx.health', { n: num(a.health_score, { maximumFractionDigits: 1 }) }) : null,
      a.symptoms?.length ? a.symptoms.map((x) => x.replace(/_/g, ' ')).join(', ') : null,
      systemNote(a.note, t),
    ].filter(Boolean)
    return { title: a.subject, detail: bits.length ? bits.join(' · ') : null }
  }
  const group = a.type === 'issue' ? 'issueState' : 'taskStatus'
  const state = (v: string) => te(group, v)
  const what =
    a.from_state == null
      ? t(a.type === 'issue' ? 'recx.openedAs' : 'recx.createdAs', { state: state(a.to_state ?? '') })
      : a.from_state === a.to_state
        ? t('recx.updated')
        : `${state(a.from_state)} → ${state(a.to_state ?? '')}`
  const note = systemNote(a.note, t)
  return { title: a.subject, detail: note ? `${what} — ${note}` : what }
}

/** The few notes the server writes itself (never a person's words), in the reader's language; anything else as typed. */
export function systemNote(note: string | null | undefined, t: T): string | null {
  if (!note) return null
  if (note === 'Issue opened') return t('recx.note.issueOpened')
  if (note === 'Task created') return t('recx.note.taskCreated')
  const schedule = /^Created by the schedule '(.*)'$/.exec(note)
  if (schedule) return t('recx.note.bySchedule', { name: schedule[1] })
  const cancelled = /^Cancelled when (\S+) was closed$/.exec(note)
  if (cancelled) return t('recx.note.cancelledWith', { key: cancelled[1] })
  return note
}
