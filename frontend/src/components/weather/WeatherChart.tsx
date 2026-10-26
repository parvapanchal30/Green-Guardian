import type { Forecast } from '../../api/types'
import { useI18n, type TKey } from '../../i18n'

export type WeatherMetric = 'temp' | 'rain' | 'water' | 'soil'

const W = 660
const H = 220
const L = 46
const R = 14
const TOP = 22
const BOTTOM = 176

type Hour = Forecast['hourly'][number]
const VALUE: Record<WeatherMetric, (h: Hour) => number | null> = {
  temp: (h) => h.temperature_c,
  rain: (h) => h.precipitation_mm,
  water: (h) => h.et0_mm,
  soil: (h) => h.soil_moisture['0_to_1cm'] ?? null,
}
const DIGITS: Record<WeatherMetric, number> = { temp: 0, rain: 1, water: 2, soil: 2 }

/**
 * One day of the hourly forecast for one measure (ADR-075). Rain is drawn as bars (millimetres per hour) with its
 * chance as a line; the others as a line. Every label is a forecast figure; nothing is filled in between hours.
 */
export function WeatherChart({ hours, metric }: { hours: Hour[]; metric: WeatherMetric }) {
  const { t, fmt } = useI18n()
  const points = hours.map((h, i) => ({ i, hour: h.time.slice(11, 16), v: VALUE[metric](h), chance: h.precipitation_probability_pct }))
  const known = points.filter((p) => p.v !== null) as { i: number; hour: string; v: number; chance: number | null }[]
  const unit = t(`weather.unit.${metric}` as TKey)
  if (known.length === 0) return <p className="py-8 text-sm text-ink-2">{t('weather.chartNone')}</p>

  const vals = known.map((p) => p.v)
  let lo = metric === 'rain' ? 0 : Math.min(...vals)
  let hi = metric === 'rain' ? Math.max(1, ...vals) : Math.max(...vals)
  if (hi - lo < 1e-9) {
    lo -= metric === 'temp' ? 2 : 0.05
    hi += metric === 'temp' ? 2 : 0.05
  }
  const pad = metric === 'rain' ? 0 : (hi - lo) * 0.15
  lo = metric === 'rain' || metric === 'water' ? Math.max(0, lo - pad) : lo - pad
  hi += pad
  const step = (W - L - R) / Math.max(1, hours.length)
  const x = (i: number) => L + step * (i + 0.5)
  const y = (v: number) => BOTTOM - ((BOTTOM - TOP) * (v - lo)) / (hi - lo)
  const yPct = (v: number) => BOTTOM - ((BOTTOM - TOP) * v) / 100
  const show = (v: number) => fmt.number(v, { maximumFractionDigits: DIGITS[metric], minimumFractionDigits: DIGITS[metric] })
  const peak = known.reduce((a, b) => (b.v > a.v ? b : a))
  const low = known.reduce((a, b) => (b.v < a.v ? b : a))
  const label = t('weather.chartLabel', { what: t(`weather.metric.${metric}` as TKey), low: `${show(low.v)} ${unit}`, high: `${show(peak.v)} ${unit}`, at: peak.hour })
  const every = Math.max(1, Math.round(hours.length / 8))

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={label}>
      {[lo, (lo + hi) / 2, hi].map((v, k) => (
        <g key={k}>
          <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke={k === 0 ? 'var(--color-line)' : 'var(--color-line-soft)'} />
          <text x={L - 6} y={y(v) + 4} textAnchor="end" fontSize="10" fontFamily="var(--font-mono)" fill="var(--color-ink-2)">{show(v)}</text>
        </g>
      ))}
      {metric === 'rain' &&
        known.map((p) => (
          <rect key={`b${p.i}`} x={x(p.i) - step * 0.35} y={y(p.v)} width={step * 0.7} height={Math.max(0, BOTTOM - y(p.v))} rx="1.5" fill="var(--color-info)" opacity="0.8">
            <title>{`${p.hour} · ${show(p.v)} ${unit}`}</title>
          </rect>
        ))}
      {metric === 'rain' && points.some((p) => p.chance !== null) && (
        <polyline
          points={points.filter((p) => p.chance !== null).map((p) => `${x(p.i)},${yPct(p.chance as number)}`).join(' ')}
          fill="none" stroke="var(--color-ink-2)" strokeWidth="1.5" strokeDasharray="4 3"
        />
      )}
      {metric !== 'rain' && known.length > 1 && (
        <polyline points={known.map((p) => `${x(p.i)},${y(p.v)}`).join(' ')} fill="none" stroke={metric === 'temp' ? 'var(--color-soil)' : 'var(--color-moss)'} strokeWidth="2.2" strokeLinejoin="round" />
      )}
      {metric !== 'rain' &&
        known.filter((p) => p.i % every === 0 || p === peak).map((p) => (
          <g key={`p${p.i}`}>
            <circle cx={x(p.i)} cy={y(p.v)} r={p === peak ? 4.5 : 3} fill="var(--color-surface)" stroke={metric === 'temp' ? 'var(--color-soil)' : 'var(--color-moss)'} strokeWidth="2" />
            <text x={x(p.i)} y={y(p.v) - 9} textAnchor="middle" fontSize="11" fill="var(--color-ink)">{show(p.v)}</text>
          </g>
        ))}
      {points.filter((p) => p.i % every === 0).map((p) => (
        <text key={`h${p.i}`} x={x(p.i)} y={BOTTOM + 18} textAnchor="middle" fontSize="10" fontFamily="var(--font-mono)" fill="var(--color-ink-2)">{p.hour}</text>
      ))}
      <text x={W - R} y={H - 4} textAnchor="end" fontSize="11" fill="var(--color-ink-2)">
        {metric === 'rain' ? t('weather.rainLegend', { unit }) : unit}
      </text>
    </svg>
  )
}
