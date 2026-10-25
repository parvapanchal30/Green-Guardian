import type { Verification } from '../api/types'
import { useI18n } from '../i18n'
import { MethodBadge } from './domain'
import { StatusChip, type Tone } from './StatusChip'

const TONE: Record<Verification['status'], Tone> = {
  not_applicable: 'neutral',
  awaiting_follow_up: 'building',
  improved: 'live',
  unchanged: 'at-risk',
  worse: 'critical',
  observed_without_score: 'neutral',
}

/**
 * Did the work help? A RULE over recorded health scores (ADR-059), shown with its inputs so nobody mistakes it for a
 * diagnosis: the score before the first action, the latest score after the last one, and the threshold used.
 */
export function VerificationCard({ v }: { v: Verification }) {
  const { t, te, fmt } = useI18n()
  if (v.status === 'not_applicable') return null
  const score = (n: number | null) => (n == null ? t('verify.noScore') : fmt.number(n, { maximumFractionDigits: 1 }))
  return (
    <section aria-labelledby="verify" className="rounded-lg border border-line bg-surface p-4">
      <h2 id="verify" className="mb-2 flex flex-wrap items-center gap-2 font-semibold">
        {t('verify.title')}
        <StatusChip tone={TONE[v.status]}>{te('verifyStatus', v.status)}</StatusChip>
        <MethodBadge method="rule" />
      </h2>
      <dl className="grid gap-2 text-sm sm:grid-cols-3">
        <div><dt className="text-xs text-ink-3">{t('verify.actions')}</dt><dd>{v.actions}{v.last_action_at && <span className="text-ink-3"> · {t('verify.lastAt', { when: fmt.dateTime(v.last_action_at) })}</span>}</dd></div>
        <div><dt className="text-xs text-ink-3">{t('verify.before')}</dt><dd>{score(v.baseline_score)}{v.baseline_at && <span className="text-ink-3"> · {fmt.dateTime(v.baseline_at)}</span>}</dd></div>
        <div><dt className="text-xs text-ink-3">{t('verify.after')}</dt><dd>{v.follow_up_at ? <>{score(v.follow_up_score)} <span className="text-ink-3">· {fmt.dateTime(v.follow_up_at)}</span></> : t('verify.notYet')}</dd></div>
      </dl>
      {v.change != null && <p className="mt-2 text-sm">{t('verify.change', { change: `${v.change > 0 ? '+' : ''}${fmt.number(v.change, { maximumFractionDigits: 1 })}` })}</p>}
      <p className="mt-2 text-xs text-ink-3">
        {t('verify.explain', { min: v.min_change })}{v.required_for_success ? ` ${t('verify.required')}` : ''}
      </p>
    </section>
  )
}
