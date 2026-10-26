import { Link } from 'react-router-dom'
import type { Asset } from '../../api/types'
import { useI18n } from '../../i18n'
import { useEvidence } from '../../lib/slice'
import { HealthChip } from '../domain'
import { EvidenceImage } from '../EvidenceGallery'
import { Icon } from '../icons'
import { Tag } from '../ui'

/**
 * A plant as a photo card (ADR-073, Canopy idea 3): its latest photo, health, stage and where it is. Used only on the
 * Trees, Plants and Crop batches tabs; the "All" tab keeps the ledger table. The whole card opens the plant.
 */
export function AssetCard({ ws, asset }: { ws: string; asset: Asset }) {
  const { t, te, fmt } = useI18n()
  const photos = useEvidence(ws, { asset_id: asset.id, limit: 1 })
  const latest = photos.data?.items[0]
  const where = [asset.species_name, asset.location_name].filter(Boolean).join(' · ')
  const { open_issue_count: issues, open_task_count: tasks } = asset.state

  return (
    <li className="relative flex flex-col overflow-hidden rounded-lg border border-line bg-surface focus-within:ring-2 focus-within:ring-moss hover:border-ink-3">
      <div className="relative aspect-[16/9] bg-surface-2 min-[480px]:aspect-[4/3]">
        {latest ? (
          <EvidenceImage ws={ws} ev={latest} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-1 text-ink-3">
            <Icon name="photo" size={26} />
            <span className="text-xs">{t('asset2.noPhoto')}</span>
          </div>
        )}
        <span className="absolute top-2 left-2"><HealthChip band={asset.state.health_band} score={asset.state.health_score} /></span>
      </div>
      <div className="flex flex-1 flex-col gap-1 p-3">
        <div className="flex items-start justify-between gap-2">
          <Link to={`/w/${ws}/assets/${asset.id}`} className="font-display text-[17px] leading-snug font-semibold outline-none after:absolute after:inset-0 hover:underline">
            {asset.label}
          </Link>
          {asset.tag_code && <Tag>{asset.tag_code}</Tag>}
        </div>
        {where && <p className="text-[13px] text-ink-2">{where}</p>}
        <p className="text-[13px] text-ink-2">
          {te('stage', asset.current_stage)}
          {!asset.is_active && <span className="ml-1 text-ink-3">{t('assets.left')}</span>}
          {asset.estimated_count != null && <> · {t('list.plantsCount', { count: asset.estimated_count, n: fmt.number(asset.estimated_count) })}</>}
          {' · '}
          {asset.state.last_observed_at ? t('list.seen', { when: fmt.relative(asset.state.last_observed_at) }) : t('list.neverSeen')}
        </p>
        {(issues > 0 || tasks > 0) && (
          <p className="mt-auto flex gap-3 pt-1 text-[13px]">
            {issues > 0 && <span className="text-critical">{t('list.openIssues', { count: issues })}</span>}
            {tasks > 0 && <span className="text-ink-2">{t('list.openTasks', { count: tasks })}</span>}
          </p>
        )}
      </div>
    </li>
  )
}
