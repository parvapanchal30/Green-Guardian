import { useEffect, useRef } from 'react'
import type { Asset, Role } from '../../api/types'
import { useI18n } from '../../i18n'
import { ActionForm } from '../ActionPanel'
import { EvidenceUploader } from '../EvidenceGallery'
import { Icon } from '../icons'
import { LifecyclePanel } from '../LifecyclePanel'
import { Tag } from '../ui'
import { ObservationForm } from './ObservationForm'

export type RecordTab = 'observation' | 'work' | 'stage' | 'photo'

/**
 * One place to record anything about a plant (ADR-072): what you see, work done, a stage change or a photo. It
 * replaces the four forms that used to be open on the plant page at all times. A modal dialog: Esc or Close ends it,
 * focus starts in the chosen tab's first field.
 */
export function RecordSheet({
  ws, asset, role, tab, onTab, onClose, issueOptions,
}: {
  ws: string
  asset: Asset
  role: Role
  tab: RecordTab
  onTab: (tab: RecordTab) => void
  onClose: () => void
  issueOptions?: { id: string; label: string }[]
}) {
  const { t } = useI18n()
  const body = useRef<HTMLDivElement>(null)
  const tabs: { id: RecordTab; label: string; show: boolean }[] = [
    { id: 'observation', label: t('asset2.tab.observation'), show: true },
    { id: 'work', label: t('asset2.tab.work'), show: asset.is_active },
    { id: 'stage', label: t('asset2.tab.stage'), show: true },
    { id: 'photo', label: t('asset2.tab.photo'), show: true },
  ]

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  useEffect(() => {
    body.current?.querySelector<HTMLElement>('input, select, textarea')?.focus()
  }, [tab])

  return (
    <div className="fixed inset-0 z-50 flex items-end bg-ink/45 sm:items-start sm:justify-center sm:pt-10" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-labelledby="record-sheet-title" className="flex max-h-[92vh] w-full flex-col rounded-t-2xl bg-surface shadow-xl sm:max-w-2xl sm:rounded-xl">
        <div className="px-5 pt-4 sm:px-6">
          <div className="flex items-center gap-2.5">
            {asset.tag_code && <Tag>{asset.tag_code}</Tag>}
            <span className="text-sm text-ink-2">{[asset.species_name, asset.location_name].filter(Boolean).join(' · ')}</span>
            <button type="button" onClick={onClose} aria-label={t('navx.close')} className="ml-auto flex h-11 w-11 items-center justify-center rounded-md hover:bg-surface-2">
              <Icon name="close" size={20} />
            </button>
          </div>
          <h2 id="record-sheet-title" className="text-[26px] font-bold">{t('asset2.sheetTitle', { name: asset.label })}</h2>
          <div role="tablist" aria-label={t('asset2.sheetTabs')} className="mt-1 flex gap-5 overflow-x-auto border-b border-line-soft">
            {tabs.filter((x) => x.show).map((x) => (
              <button
                key={x.id}
                type="button"
                role="tab"
                id={`record-tab-${x.id}`}
                aria-selected={tab === x.id}
                aria-controls="record-panel"
                onClick={() => onTab(x.id)}
                className={`-mb-px border-b-2 py-3 text-[15px] whitespace-nowrap ${tab === x.id ? 'border-moss font-semibold text-ink' : 'border-transparent text-ink-2 hover:text-ink'}`}
              >
                {x.label}
              </button>
            ))}
          </div>
        </div>
        <div ref={body} id="record-panel" role="tabpanel" aria-labelledby={`record-tab-${tab}`} className="overflow-y-auto px-5 py-4 sm:px-6">
          {tab === 'observation' && <ObservationForm ws={ws} assetId={asset.id} onCreated={onClose} />}
          {tab === 'work' && <ActionForm ws={ws} assetId={asset.id} onDone={onClose} />}
          {tab === 'stage' && <LifecyclePanel ws={ws} asset={asset} role={role} show="form" onDone={onClose} />}
          {tab === 'photo' && <EvidenceUploader ws={ws} assetId={asset.id} issueOptions={issueOptions} onUploaded={onClose} />}
        </div>
      </div>
    </div>
  )
}
