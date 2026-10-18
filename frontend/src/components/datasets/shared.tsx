import type { DatasetItem, DatasetStatus, ImageOrigin, LabelStatus } from '../../api/types'
import { label } from '../../lib/format'
import { StatusChip, type Tone } from '../StatusChip'

/** Said wherever a review is shown: the application records who decided, it cannot verify who is qualified. */
export const UNVERIFIED_NOTE =
  'Reviewers are not verified as qualified. A decision here means a signed-in user recorded it with written evidence; it is not expert validation.'

const STATUS_TONE: Record<DatasetStatus, Tone> = { proposed: 'building', under_review: 'at-risk', approved: 'live', rejected: 'critical' }
const STATUS_TEXT: Record<DatasetStatus, string> = {
  proposed: 'Candidate: proposed',
  under_review: 'Candidate: under review',
  approved: 'Approved',
  rejected: 'Rejected',
}

export function DatasetStatusChip({ status }: { status: DatasetStatus }) {
  return <StatusChip tone={STATUS_TONE[status]}>{STATUS_TEXT[status]}</StatusChip>
}

export const isApproved = (d: Pick<DatasetItem, 'status'>) => d.status === 'approved'

const ORIGIN_TEXT: Record<ImageOrigin, { text: string; tone: Tone; explain: string }> = {
  publisher_created: { text: 'Images made by the publisher', tone: 'live', explain: 'The publisher took the images, so their licence covers them.' },
  third_party_licensed: { text: 'Third-party images, licences documented', tone: 'live', explain: 'The publisher documents the licence or permission of each third-party image.' },
  third_party_scraped: { text: 'Images scraped from third parties', tone: 'critical', explain: 'A publisher’s licence only covers images the publisher had the right to license. Scraped images cannot be approved without written confirmation of those rights.' },
  unknown: { text: 'Image origin unknown', tone: 'at-risk', explain: 'Who made the images, and with what permission, is not established. Approval is blocked until it is.' },
}

export function OriginChip({ origin }: { origin: ImageOrigin }) {
  return <StatusChip tone={ORIGIN_TEXT[origin].tone}>{ORIGIN_TEXT[origin].text}</StatusChip>
}
export const originExplanation = (o: ImageOrigin) => ORIGIN_TEXT[o].explain

const LABEL_TONE: Record<LabelStatus, Tone> = { unreviewed: 'neutral', under_review: 'at-risk', accepted: 'live', rejected: 'critical', corrected: 'building' }
/** Never "validated": accepted means a recorded decision, nothing more. */
export function LabelStatusChip({ status }: { status: LabelStatus }) {
  return <StatusChip tone={LABEL_TONE[status]}>{label(status)}</StatusChip>
}

export function LicenceVerdictChip({ verdict }: { verdict: string }) {
  if (verdict === 'eligible') return <StatusChip tone="live">Licence eligible (provisional)</StatusChip>
  if (verdict === 'excluded') return <StatusChip tone="critical">Licence excluded by policy</StatusChip>
  if (verdict === 'needs_review') return <StatusChip tone="at-risk">Licence outside the policy</StatusChip>
  return <StatusChip tone="neutral">Synthetic fixture</StatusChip>
}

export const short = (id: string | null | undefined) => (id ? id.slice(0, 8) : '—')

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
