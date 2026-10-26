import { describe, expect, it } from 'vitest'
import { translate, type TKey } from '../i18n'
import type { AnalyticsReport, ImpactReport } from '../lib/reports'
import { analyticsSentence, impactSentence } from '../lib/summary'

/* The sentences before the report figures (ADR-077): fixed templates over the report's own numbers. */

const t = (key: TKey, params?: Record<string, string | number>) => translate('en', key, params)
const num = (v: number, o?: Intl.NumberFormatOptions) => v.toLocaleString('en', o)

const analytics = {
  issues: { opened: 3, closed: 1, still_open: 2, opened_by_category: {}, opened_by_severity: {}, closed_by_outcome: {}, median_days_to_close: 6.5 },
  tasks: { created: 8, completed: 4, cancelled: 0, completed_with_due_date: 4, completed_on_time: 3, on_time_pct: 75, overdue_now: 1, completed_by_type: {} },
  actions: { recorded: 2, by_kind: {}, top_products: [] },
  observations: { recorded: 1, with_health_score: 1, with_measurements: 0, assets_observed: 1, observers: 1, by_kind: {} },
  agent: { suggested: 0, accepted: 0, dismissed: 0, expired: 0, open_now: 0 },
} as unknown as AnalyticsReport

const impact = {
  planting: { registered: 12, planted: 10, batches_registered: 0, plants_in_batches: 0, by_species: [] },
  survival: { alive: 11, dead: 1, rate: 91.66, by_species: [] },
  health: { assets_compared: 5, healthy_share_start: 60, healthy_share_end: 80 },
  growth: { comparable_assets: 0, median_height_change_pct: null },
} as unknown as ImpactReport

describe('report sentences', () => {
  it('Analytics: issues, tasks on time and observations, singular when it is one', () => {
    expect(analyticsSentence(analytics, t, num)).toBe(
      'Issues: 3 opened, 1 closed, 2 still open. 4 of 8 tasks created were completed, 75% of those with a due date on time. 1 observation was recorded, on 1 plant.',
    )
    const noDue = { ...analytics, tasks: { ...analytics.tasks, on_time_pct: null } } as AnalyticsReport
    expect(analyticsSentence(noDue, t, num)).toContain('4 of 8 tasks created were completed.')
  })

  it('Impact: says only what the report has (no growth sentence without a comparable plant)', () => {
    const s = impactSentence(impact, t, num)
    expect(s).toBe('12 plants were registered. Survival is 91.7% (11 alive, 1 dead). The healthy share went from 60% to 80% for the 5 plants scored at both ends.')
    expect(s).not.toMatch(/height/)
  })
})
