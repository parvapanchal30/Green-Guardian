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
