import { describe, expect, it } from 'vitest'
import type { Forecast } from '../api/types'
import { dailyForecast, dayKind, rainAdvice, summarize, weekGlance } from '../lib/weather'

const hour = (iso: string, over: Partial<Forecast['hourly'][number]> = {}) => ({
  time: iso, precipitation_mm: 0, precipitation_probability_pct: 10, temperature_c: 25, et0_mm: 0.1, soil_moisture: { '0_to_1cm': 0.3 }, ...over,
})

const fc = (hourly: Forecast['hourly']): Forecast => ({
  latitude: 1, longitude: 1, timezone: 'UTC', source: 'open_meteo', attribution: 'x', fetched_at: '2026-10-07T00:00:00Z', hourly,
})

describe('summarize', () => {
  it('sums precipitation over the next 24 hours starting at the current hour, ignoring nulls', () => {
    const hs = Array.from({ length: 30 }, (_, i) =>
      hour(new Date(Date.UTC(2026, 9, 7, i)).toISOString(), { precipitation_mm: i === 3 ? null : 1, precipitation_probability_pct: i === 5 ? 90 : 10 }))
    const s = summarize(fc(hs), new Date(Date.UTC(2026, 9, 7, 2, 30)))!
    expect(s.nowIndex).toBe(2)
    expect(s.next24hPrecipMm).toBe(23) // hours 2..25, one null -> 23 values of 1.0
    expect(s.maxPrecipProbabilityPct).toBe(90)
    expect(s.soilMoisture0to1).toBe(0.3)
  })

  it('returns null when the forecast does not cover now', () => {
    const s = summarize(fc([hour('2026-10-07T00:00:00Z')]), new Date('2026-11-01T00:00:00Z'))
    expect(s).toBeNull()
  })

  it('reports unknown rather than zero when precipitation data is entirely missing', () => {
    const s = summarize(fc([hour('2026-10-07T00:00:00Z', { precipitation_mm: null, precipitation_probability_pct: null })]), new Date('2026-10-07T00:10:00Z'))!
    expect(s.next24hPrecipMm).toBeNull()
    expect(s.maxPrecipProbabilityPct).toBeNull()
  })
})

describe('days, kinds, rain advice and the week (ADR-075)', () => {
  // A place at UTC+05:30: hours carry the place's offset, so days follow its calendar.
  const at = (day: number, h: number) => `2026-10-${String(day).padStart(2, '0')}T${String(h).padStart(2, '0')}:00:00+05:30`
  const two = fc([
    hour(at(27, 0), { temperature_c: 22, precipitation_mm: 0, precipitation_probability_pct: 10 }),
    hour(at(27, 14), { temperature_c: 31, precipitation_mm: 0.1, precipitation_probability_pct: 20 }),
    hour(at(28, 3), { temperature_c: 20, precipitation_mm: 3, precipitation_probability_pct: 80 }),
    hour(at(28, 15), { temperature_c: 26, precipitation_mm: 4, precipitation_probability_pct: 60, et0_mm: null }),
  ])

  it('folds hours into the place\'s own days with highs, lows, rain sums and the highest chance', () => {
    const [d1, d2] = dailyForecast(two)
    expect(d1).toMatchObject({ date: '2026-10-27', hi: 31, lo: 22, rainMm: 0.1, rainChance: 20 })
    expect(d2).toMatchObject({ date: '2026-10-28', hi: 26, lo: 20, rainMm: 7, rainChance: 80, waterUseMm: 0.1 })
    expect(dayKind(d1)).toBe('dry')
    expect(dayKind(d2)).toBe('rain')
    expect(dayKind({ rainMm: 0, rainChance: 35 })).toBe('showers')
    expect(dayKind({ rainMm: null, rainChance: null })).toBe('unknown')
  })

  it('applies the irrigation rule\'s thresholds, the workspace\'s own when set', () => {
    const now = new Date('2026-10-27T22:00:00Z') // 03:30 on the 28th at the place, inside the 03:00 hour
    expect(rainAdvice(two, now, {})).toMatchObject({ minMm: 5, minChance: 70, rainMm: 7, chance: 80, meets: true })
    expect(rainAdvice(two, now, { agent: { irrigation_min_rain_mm: 10 } })).toMatchObject({ minMm: 10, meets: false })
    expect(rainAdvice(two, now, { agent: { irrigation_min_probability_pct: 'x' } }).minChance).toBe(70)
    expect(rainAdvice(two, new Date('2027-01-01T00:00:00Z'), {}).meets).toBeNull()
  })

  it('sums the week and names the wettest, hottest and dry days', () => {
    const w = weekGlance(dailyForecast(two))
    expect(w.rainMm).toBe(7.1)
    expect(w.wettest?.date).toBe('2026-10-28')
    expect(w.hottest?.date).toBe('2026-10-27')
    expect(w.dry.map((d) => d.date)).toEqual(['2026-10-27'])
  })
})
