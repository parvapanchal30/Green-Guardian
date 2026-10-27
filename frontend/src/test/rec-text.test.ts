import { describe, expect, it } from 'vitest'
import type { DashboardActivity, Recommendation } from '../api/types'
import { translate, type Locale, type TKey } from '../i18n'
import { activityText, recommendationText } from '../lib/recText'

/* ADR-081: suggestions and activity lines are worded in the reader's language from the server's numbers. */

const tools = (locale: Locale) => {
  const t = (key: TKey, params?: Record<string, string | number>) => translate(locale, key, params)
  const te = (group: string, value: string, fallback?: string) => {
    const out = translate(locale, `${group}.${value}`)
    return out === `${group}.${value}` ? (fallback ?? value) : out
  }
  const num = (v: number, o?: Intl.NumberFormatOptions) => v.toLocaleString(locale, o)
  return [t, te, num] as const
}

const rec = (rule_key: string, evidence: Record<string, unknown>, title = 'server English title'): Recommendation =>
  ({ id: 'r1', rule_key, method: 'rule', asset_id: 'a1', title, explanation: 'server English explanation', evidence: { evaluated_at: '2026-10-27T00:00:00Z', inputs: evidence }, proposed_action: {}, severity: 'high', status: 'open' }) as unknown as Recommendation

describe('suggestions in the reader\'s language', () => {
  it('critical health and a fall in health, in English and in Hindi', () => {
    const crit = rec('critical_health', { label: 'Gulmohar #09', score: 22, threshold: 40 })
    expect(recommendationText(crit, ...tools('en'))?.title).toBe('Gulmohar #09 health is critical (22)')
    const hi = recommendationText(crit, ...tools('hi'))!
    expect(hi.title).toBe('Gulmohar #09 का स्वास्थ्य गंभीर है (22)')
    expect(hi.explanation).toContain('गंभीर सीमा 40')
    const fell = rec('health_decline', { label: 'Neem #102', from_score: 78, to_score: 31, drop: 47, window_days: 14, observations: 3 })
    expect(recommendationText(fell, ...tools('en'))).toEqual({ title: 'Neem #102 health fell 47 points in 14 days', explanation: '78 → 31 across 3 observations' })
  })

  it('not looked at, with the basis translated; never observed has its own wording', () => {
    const gap = rec('inspection_gap', { label: 'Gulmohar #12', interval_days: 21, days_since: 70, basis: 'completed inspection task', last_attention_at: '2026-08-17T10:00:00Z' })
    const hi = recommendationText(gap, ...tools('hi'))!
    expect(hi.title).toBe('Gulmohar #12 को 70 दिनों से नहीं देखा गया (सीमा 21)')
    expect(hi.explanation).toContain('2026-08-17 को एक पूरा निरीक्षण')
    const never = rec('inspection_gap', { label: 'Okra block B', interval_days: 21, days_since: null })
    expect(recommendationText(never, ...tools('en'))?.title).toBe('Okra block B has never been observed')
  })

  it('falls back to the server\'s English when the numbers are missing (older suggestions)', () => {
    expect(recommendationText(rec('critical_health', {}), ...tools('hi'))).toBeNull()
    expect(recommendationText(rec('critical_health', { label: 'X' }), ...tools('hi'))).toBeNull()
    expect(recommendationText(rec('symptom_cluster', { label: 'X' }), ...tools('hi'))).toBeNull()
  })
})

describe('activity lines in the reader\'s language', () => {
  const base = { at: '2026-10-25T10:00:00Z', ref_id: 'x', asset_id: 'a1', title: 'English title', detail: 'English detail' }
  it('an observation shows the plant once, its score and what was seen', () => {
    const a = { ...base, type: 'observation', key: null, subject: 'Neem #102', health_score: 31, symptoms: ['leaf_yellowing'], note: 'crown thinning' } as DashboardActivity
    expect(activityText(a, ...tools('hi'))).toEqual({ title: 'Neem #102', detail: 'स्वास्थ्य 31 · leaf yellowing · crown thinning' })
  })

  it('issue and task changes use the translated states', () => {
    const opened = { ...base, type: 'issue', key: 'GG-001', subject: 'Crown dieback', from_state: null, to_state: 'open', note: null } as DashboardActivity
    expect(activityText(opened, ...tools('hi')).detail).toBe(`${translate('hi', 'issueState.open')} के रूप में खोली गई`)
    const moved = { ...base, type: 'task', key: 'T-001', subject: 'Inspect', from_state: 'todo', to_state: 'done', note: 'bark sampled' } as DashboardActivity
    expect(activityText(moved, ...tools('en')).detail).toBe(`${translate('en', 'taskStatus.todo')} → ${translate('en', 'taskStatus.done')} — bark sampled`)
  })

  it('an older server without the parts keeps its English line, without repeating the key', () => {
    const old = { ...base, type: 'task', key: 'T-001', title: 'T-001 Inspect the bark' } as DashboardActivity
    expect(activityText(old, ...tools('hi'))).toEqual({ title: 'Inspect the bark', detail: 'English detail' })
  })
})

describe('notes the server writes itself', () => {
  it('are translated; a person\'s own note stays as typed', async () => {
    const { systemNote } = await import('../lib/recText')
    const [t] = tools('hi')
    expect(systemNote('Issue opened', t)).toBe('समस्या खोली गई')
    expect(systemNote("Created by the schedule 'Monthly check of Banyan #01'", t)).toBe("समय-सारणी 'Monthly check of Banyan #01' से बनाया गया")
    expect(systemNote('Cancelled when GG-004 was closed', t)).toBe('GG-004 बंद होने पर रद्द किया गया')
    expect(systemNote('sprayed twice', t)).toBe('sprayed twice')
    expect(systemNote(null, t)).toBeNull()
  })
})
