import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { AgreementTab, ClaimsTab, QualityTab, SplitsTab } from '../components/datasets/AnalysisTabs'
import { OverviewTab } from '../components/datasets/OverviewTab'
import { SamplesTab } from '../components/datasets/SamplesTab'
import { DatasetStatusChip } from '../components/datasets/shared'
import { PageHeader } from '../components/domain'
import { ErrorState, LoadingBlock } from '../components/states'
import { StatusChip } from '../components/StatusChip'
import { useDataset } from '../lib/datasets'

const TABS = [
  { key: 'overview', text: 'Licence and approval' },
  { key: 'samples', text: 'Samples and review' },
  { key: 'quality', text: 'Quality' },
  { key: 'splits', text: 'Splits' },
  { key: 'agreement', text: 'Reviewer agreement' },
  { key: 'claims', text: 'Claim gate' },
] as const
type Tab = (typeof TABS)[number]['key']

/** Each tab fetches only when it is open, so a reader who never opens one never requests it. */
export function DatasetDetailPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const { datasetId = '' } = useParams()
  const q = useDataset(ws, datasetId)
  const [tab, setTab] = useState<Tab>('overview')
  const d = q.data

  return (
    <div className="space-y-4">
      <p className="text-sm"><Link to={`/w/${ws}/ai/datasets`} className="text-moss underline">← All datasets</Link></p>
      {q.isLoading && <LoadingBlock label="Loading dataset" />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {d && (
        <>
          <PageHeader title={`${d.name} · version ${d.version}`} subtitle={d.kind === 'synthetic' ? 'Synthetic test fixture, not biological data.' : 'Dataset record'}>
            <DatasetStatusChip status={d.status} />
            {d.kind === 'synthetic' && <StatusChip tone="neutral">Synthetic</StatusChip>}
            <StatusChip tone="neutral">{d.sample_count} registered sample{d.sample_count === 1 ? '' : 's'}</StatusChip>
          </PageHeader>
          <div role="tablist" aria-label="Dataset sections" className="flex flex-wrap gap-1 border-b border-line">
            {TABS.map((t) => (
              <button
                key={t.key}
                role="tab"
                type="button"
                aria-selected={tab === t.key}
                onClick={() => setTab(t.key)}
                className={`rounded-t border border-b-0 px-3 py-1.5 text-sm ${tab === t.key ? 'border-line bg-surface font-medium' : 'border-transparent text-ink-2 hover:bg-surface-2'}`}
              >
                {t.text}
              </button>
            ))}
          </div>
          <div role="tabpanel" aria-label={TABS.find((t) => t.key === tab)?.text}>
            {tab === 'overview' && <OverviewTab ws={ws} d={d} role={workspace.role} />}
            {tab === 'samples' && <SamplesTab ws={ws} d={d} role={workspace.role} />}
            {tab === 'quality' && <QualityTab ws={ws} d={d} />}
            {tab === 'splits' && <SplitsTab ws={ws} d={d} role={workspace.role} />}
            {tab === 'agreement' && <AgreementTab ws={ws} d={d} />}
            {tab === 'claims' && <ClaimsTab ws={ws} d={d} />}
          </div>
        </>
      )}
    </div>
  )
}
