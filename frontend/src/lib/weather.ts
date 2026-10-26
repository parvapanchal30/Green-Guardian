import type { Forecast } from '../api/types'

export interface WeatherSummary {
  nowIndex: number
  temperatureC: number | null
  soilMoisture0to1: number | null
  next24hPrecipMm: number | null
  maxPrecipProbabilityPct: number | null
}

const sum = (xs: (number | null)[]) => {
  const v = xs.filter((x): x is number => x !== null)
  return v.length ? Math.round(v.reduce((a, b) => a + b, 0) * 10) / 10 : null
}

/** Summarise a forecast from the hour containing `now`. Returns null if the forecast does not cover `now`. */
export function summarize(fc: Forecast, now: Date): WeatherSummary | null {
  const t = now.getTime()
  let idx = -1
  for (let i = 0; i < fc.hourly.length; i++) {
    const start = new Date(fc.hourly[i].time).getTime()
    if (start <= t && t < start + 3_600_000) {
      idx = i
      break
    }
  }
  if (idx < 0) return null
  const next = fc.hourly.slice(idx, idx + 24)
  const probs = next.map((h) => h.precipitation_probability_pct).filter((x): x is number => x !== null)
  return {
    nowIndex: idx,
    temperatureC: fc.hourly[idx].temperature_c,
    soilMoisture0to1: fc.hourly[idx].soil_moisture['0_to_1cm'] ?? null,
    next24hPrecipMm: sum(next.map((h) => h.precipitation_mm)),
    maxPrecipProbabilityPct: probs.length ? Math.max(...probs) : null,
  }
}

export interface DayForecast {
  /** The place's local calendar date, YYYY-MM-DD (taken from the forecast's own times). */
  date: string
  hi: number | null
  lo: number | null
  rainMm: number | null
  /** Highest hourly chance of rain that day, percent. */
  rainChance: number | null
  waterUseMm: number | null
  hours: Forecast['hourly']
}

const round1 = (x: number) => Math.round(x * 10) / 10
const nums = (xs: (number | null | undefined)[]) => xs.filter((x): x is number => x !== null && x !== undefined)

/**
 * Hourly forecast folded into days of the place's own calendar (ADR-075). Hours carry the place's UTC offset, so the
 * first ten characters are its local date. Figures are the forecast's own: sums and extremes, nothing smoothed.
 */
export function dailyForecast(fc: Forecast): DayForecast[] {
  const byDay = new Map<string, Forecast['hourly']>()
  for (const h of fc.hourly) byDay.set(h.time.slice(0, 10), [...(byDay.get(h.time.slice(0, 10)) ?? []), h])
  return [...byDay.entries()].map(([date, hours]) => {
    const temps = nums(hours.map((h) => h.temperature_c))
    const chances = nums(hours.map((h) => h.precipitation_probability_pct))
    return {
      date,
      hi: temps.length ? Math.max(...temps) : null,
      lo: temps.length ? Math.min(...temps) : null,
      rainMm: sum(hours.map((h) => h.precipitation_mm)),
      rainChance: chances.length ? Math.max(...chances) : null,
      waterUseMm: sum(hours.map((h) => h.et0_mm)),
      hours,
    }
  })
}

export type DayKind = 'dry' | 'showers' | 'rain' | 'unknown'

/** A day described by its rain only (the forecast has no cloud cover): words and icon follow from these thresholds. */
export function dayKind(d: Pick<DayForecast, 'rainMm' | 'rainChance'>): DayKind {
  if (d.rainMm === null && d.rainChance === null) return 'unknown'
  if ((d.rainMm ?? 0) >= 1 && (d.rainChance ?? 0) >= 50) return 'rain'
  if ((d.rainChance ?? 0) >= 30 || (d.rainMm ?? 0) >= 0.2) return 'showers'
  return 'dry'
}

export interface RainAdvice {
  minMm: number
  minChance: number
  rainMm: number | null
  chance: number | null
  /** True when the forecast here meets both thresholds of the irrigation_defer rule. */
  meets: boolean | null
}

/**
 * The irrigation_defer rule's test applied to this place's next 24 hours (RULE, not a prediction of its own). The
 * thresholds are the workspace's agent settings, defaulting like the server (backend AgentSettings: 5 mm, 70 %).
 */
export function rainAdvice(fc: Forecast, now: Date, settings: Record<string, unknown> | undefined): RainAdvice {
  const agent = (settings?.agent ?? {}) as Record<string, unknown>
  const positive = (v: unknown, d: number) => (typeof v === 'number' && v > 0 ? v : typeof v === 'string' && Number(v) > 0 ? Number(v) : d)
  const minMm = positive(agent.irrigation_min_rain_mm, 5)
  const minChance = positive(agent.irrigation_min_probability_pct, 70)
  const s = summarize(fc, now)
  const rainMm = s?.next24hPrecipMm ?? null
  const chance = s?.maxPrecipProbabilityPct ?? null
  return { minMm, minChance, rainMm, chance, meets: rainMm === null || chance === null ? null : rainMm >= minMm && chance >= minChance }
}

/** The week in a few figures: total rain, the wettest and hottest days, and the days unlikely to see rain. */
export function weekGlance(days: DayForecast[]) {
  const withRain = days.filter((d) => d.rainMm !== null)
  const wettest = withRain.length ? withRain.reduce((a, b) => ((b.rainMm ?? 0) > (a.rainMm ?? 0) ? b : a)) : null
  const withHi = days.filter((d) => d.hi !== null)
  const hottest = withHi.length ? withHi.reduce((a, b) => ((b.hi ?? 0) > (a.hi ?? 0) ? b : a)) : null
  return {
    rainMm: withRain.length ? round1(withRain.reduce((a, d) => a + (d.rainMm ?? 0), 0)) : null,
    wettest: wettest && (wettest.rainMm ?? 0) > 0 ? wettest : null,
    hottest,
    dry: days.filter((d) => dayKind(d) === 'dry'),
  }
}
