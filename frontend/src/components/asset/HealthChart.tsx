import type { Observation } from '../../api/types'
import { useI18n } from '../../i18n'

const W = 600
const H = 190
const L = 38 // left margin for the axis labels
const R = 12
const TOP = 10
const BOTTOM = 160
const y = (v: number) => BOTTOM - ((BOTTOM - TOP) * v) / 100

/**
 * Recorded health scores over time on the three bands, with the days work was done marked. A drawing of what was
 * recorded: nothing between two scores is estimated, and no line continues past the latest score.
 */
export function HealthChart({ observations, workDays = [] }: { observations: Observation[]; workDays?: string[] }) {
  const { t, fmt } = useI18n()
  const scored = observations.filter((o) => o.health_score != null).sort((a, b) => a.observed_at.localeCompare(b.observed_at))
  if (scored.length === 0) return <p className="text-sm text-ink-2">{t('asset2.chartNone')}</p>
  const t0 = new Date(scored[0].observed_at).getTime()
  const t1 = Math.max(new Date(scored[scored.length - 1].observed_at).getTime(), ...workDays.map((d) => new Date(d).getTime()), t0 + 86_400_000)
  const x = (iso: string) => L + ((W - L - R) * (new Date(iso).getTime() - t0)) / (t1 - t0)
  const pts = scored.map((o) => ({ x: x(o.observed_at), y: y(o.health_score as number), o }))
  const first = scored[0]
  const last = scored[scored.length - 1]
  const label = t('asset2.chartLabel', { count: scored.length, from: fmt.date(first.observed_at), to: fmt.date(last.observed_at), latest: Math.round(last.health_score as number) })
  const dot = (v: number) => (v >= 70 ? 'var(--color-healthy)' : v >= 40 ? 'var(--color-at-risk)' : 'var(--color-critical)')

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={label}>
      <rect x={L} y={y(100)} width={W - L - R} height={y(70) - y(100)} fill="var(--color-healthy-soft)" />
      <rect x={L} y={y(70)} width={W - L - R} height={y(40) - y(70)} fill="var(--color-at-risk-soft)" />
      <rect x={L} y={y(40)} width={W - L - R} height={y(0) - y(40)} fill="var(--color-critical-soft)" />
      {[100, 70, 40, 0].map((v) => (
        <text key={v} x={L - 6} y={y(v) + 4} textAnchor="end" fontSize="10" fontFamily="var(--font-mono)" fill="var(--color-ink-2)">{v}</text>
      ))}
      {workDays.map((d) => (
        <g key={d}>
          <line x1={x(d)} x2={x(d)} y1={TOP} y2={BOTTOM} stroke="var(--color-moss)" strokeWidth="1.5" strokeDasharray="3 3" />
          <text x={x(d) - 4} y={TOP + 12} textAnchor="end" fontSize="11" fill="var(--color-moss)">{t('asset2.work')}</text>
        </g>
      ))}
      {pts.length > 1 && <polyline points={pts.map((p) => `${p.x},${p.y}`).join(' ')} fill="none" stroke="var(--color-ink)" strokeWidth="2" />}
      {pts.map((p) => (
        <circle key={p.o.id} cx={p.x} cy={p.y} r="5" fill={dot(p.o.health_score as number)} stroke="var(--color-surface)" strokeWidth="2">
          <title>{`${fmt.date(p.o.observed_at)} · ${Math.round(p.o.health_score as number)}`}</title>
        </circle>
      ))}
      <text x={L} y={H - 8} fontSize="10" fontFamily="var(--font-mono)" fill="var(--color-ink-2)">{fmt.date(first.observed_at)}</text>
      <text x={W - R} y={H - 8} textAnchor="end" fontSize="10" fontFamily="var(--font-mono)" fill="var(--color-ink-2)">{fmt.date(last.observed_at)}</text>
    </svg>
  )
}
