import type { DatasetItem, DatasetStatus, ImageOrigin, LabelStatus } from '../../api/types'
import { useI18n } from '../../i18n'
import { StatusChip, type Tone } from '../StatusChip'

// The note that reviewers are not verified as qualified is the catalog entry `ds.unverifiedNote`:
// it is shown wherever a review is, because the application records who decided, not who is qualified.

const STATUS_TONE: Record<DatasetStatus, Tone> = { proposed: 'building', under_review: 'at-risk', approved: 'live', rejected: 'critical' }

export function DatasetStatusChip({ status }: { status: DatasetStatus }) {
  const { te } = useI18n()
  return <StatusChip tone={STATUS_TONE[status]}>{te('datasetStatus', status)}</StatusChip>
}

export const isApproved = (d: Pick<DatasetItem, 'status'>) => d.status === 'approved'

const ORIGIN_TONE: Record<ImageOrigin, Tone> = { publisher_created: 'live', third_party_licensed: 'live', third_party_scraped: 'critical', unknown: 'at-risk' }

export function OriginChip({ origin }: { origin: ImageOrigin }) {
  const { te } = useI18n()
  return <StatusChip tone={ORIGIN_TONE[origin]}>{te('imageOrigin', origin)}</StatusChip>
}

const LABEL_TONE: Record<LabelStatus, Tone> = { unreviewed: 'neutral', under_review: 'at-risk', accepted: 'live', rejected: 'critical', corrected: 'building' }
/** Never "validated": accepted means a recorded decision, nothing more. */
export function LabelStatusChip({ status }: { status: LabelStatus }) {
  const { te } = useI18n()
  return <StatusChip tone={LABEL_TONE[status]}>{te('labelStatus', status)}</StatusChip>
}

export function LicenceVerdictChip({ verdict }: { verdict: string }) {
  const { t } = useI18n()
  if (verdict === 'eligible') return <StatusChip tone="live">{t('ds.verdict.eligible')}</StatusChip>
  if (verdict === 'excluded') return <StatusChip tone="critical">{t('ds.verdict.excluded')}</StatusChip>
  if (verdict === 'needs_review') return <StatusChip tone="at-risk">{t('ds.verdict.needs_review')}</StatusChip>
  return <StatusChip tone="neutral">{t('ds.verdict.synthetic')}</StatusChip>
}

/** Last 8 characters: identifiers are time-ordered UUIDs whose first characters are shared by everything created together. */
export const short = (id: string | null | undefined) => (id ? id.slice(-8) : '—')

/** Only https links are rendered as links; anything else is shown as plain text. */
export function SafeUrl({ url }: { url: string }) {
  return url.startsWith('https://') ? (
    <a href={url} target="_blank" rel="noreferrer noopener" className="break-all text-moss underline">{url}</a>
  ) : (
    <span className="break-all">{url}</span>
  )
}

export function Fact({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-ink-3">{name}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  )
}
