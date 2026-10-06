import type { ReactNode } from 'react'
import type { Capability, Stage } from '../api/types'
import { StatusChip } from './StatusChip'
import { LoadingBlock } from './states'

const STAGE_TEXT: Record<Stage, string> = { mvp: 'MVP', v2: 'V2 · Prediction', v3: 'V3 · Recommendation', v4: 'V4 · Optimization' }

export function ComingSoonPanel({
  title,
  summary,
  technique,
  stage,
  reason,
  children,
}: {
  title: string
  summary?: string
  technique?: string
  stage?: Stage
  reason?: string | null
  /** A real layout of the future feature: controls stay disabled and no result is ever shown. */
  children?: ReactNode
}) {
  const inDevelopment = stage === 'mvp'
  return (
    <section aria-labelledby="soon-title" className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="soon-title" className="text-xl font-semibold">
          {title}
        </h2>
        <StatusChip tone={inDevelopment ? 'building' : 'soon'}>{inDevelopment ? 'In development' : 'Coming soon'}</StatusChip>
        {stage && <StatusChip tone="neutral">{STAGE_TEXT[stage]}</StatusChip>}
        {technique && <StatusChip tone="neutral">Powered by: {technique}</StatusChip>}
      </div>
      {summary && <p className="max-w-prose text-ink-2">{summary}</p>}
      {children && (
        <div
          aria-disabled="true"
          className="pointer-events-none select-none rounded-lg border border-dashed border-line bg-surface p-4 opacity-60"
        >
          <fieldset disabled className="contents">
            {children}
          </fieldset>
        </div>
      )}
      <p className="text-sm text-ink-3">
        {reason ? `${reason}. ` : ''}No result is computed or displayed here until this feature is live.
      </p>
    </section>
  )
}

/**
 * Renders `children` (the live feature) only when the backend reports the capability as available;
 * otherwise a real-layout "Coming soon" panel. Never renders children for an unavailable capability.
 */
export function CapabilityGate({
  feature,
  capabilities,
  title,
  summary,
  preview,
  children,
}: {
  feature: string
  capabilities: Capability[] | undefined
  title: string
  summary?: string
  preview?: ReactNode
  children: ReactNode
}) {
  if (!capabilities) return <LoadingBlock label="Checking availability" />
  const cap = capabilities.find((c) => c.key === feature)
  if (cap?.available) return <>{children}</>
  return (
    <ComingSoonPanel
      title={title}
      summary={summary}
      technique={cap?.technique}
      stage={cap?.stage}
      reason={cap?.reason ?? (cap ? null : 'Not registered with the server')}
    >
      {preview}
    </ComingSoonPanel>
  )
}
