import { describe, expect, it } from 'vitest'
import type { Forecast } from '../api/types'
import { summarize } from '../lib/weather'

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
