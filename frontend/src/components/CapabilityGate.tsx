import type { ReactNode } from 'react'
import type { Capability, Stage } from '../api/types'
import { useI18n } from '../i18n'
import { StatusChip } from './StatusChip'
import { LoadingBlock } from './states'

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
  const { t, te } = useI18n()
  const inDevelopment = stage === 'mvp'
  return (
    <section aria-labelledby="soon-title" className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="soon-title" className="text-xl font-semibold">
          {title}
        </h2>
        <StatusChip tone={inDevelopment ? 'building' : 'soon'}>{inDevelopment ? t('soon.inDevelopment') : t('soon.comingSoon')}</StatusChip>
        {stage && <StatusChip tone="neutral">{te('soon.stage', stage)}</StatusChip>}
        {/* The technique and reason come from the server and are shown as sent. */}
        {technique && <StatusChip tone="neutral">{t('soon.poweredBy', { technique })}</StatusChip>}
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
        {reason ? `${reason}. ` : ''}{t('soon.noResult')}
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
  const { t } = useI18n()
  if (!capabilities) return <LoadingBlock label={t('soon.checking')} />
  const cap = capabilities.find((c) => c.key === feature)
  if (cap?.available) return <>{children}</>
  return (
    <ComingSoonPanel
      title={title}
      summary={summary}
      technique={cap?.technique}
      stage={cap?.stage}
      reason={cap?.reason ?? (cap ? null : t('soon.notRegistered'))}
    >
      {preview}
    </ComingSoonPanel>
  )
}
