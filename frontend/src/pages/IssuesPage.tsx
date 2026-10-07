import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { PageHeader, Pagination, SeverityChip, StateChip, input } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock } from '../components/states'
import { label, relative } from '../lib/format'
import { useIssues } from '../lib/slice'

const PAGE = 25

export function IssuesPage() {
  const { ws } = useWorkspaceCtx()
  const [scope, setScope] = useState<'open' | 'closed' | 'all'>('open')
  const [severity, setSeverity] = useState('')
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)
  const list = useIssues(ws, { is_open: scope === 'all' ? undefined : scope === 'open', severity: severity || undefined, q, limit: PAGE, offset })

  return (
    <div>
      <PageHeader title="Botanical issues" subtitle="Structured problems with severity, evidence, an owner and a lifecycle. Open one from an asset or from a suggestion." />
      <div className="mb-3 flex flex-wrap items-center gap-2" role="search">
        <div role="group" aria-label="Scope" className="flex overflow-hidden rounded border border-line text-sm">
          {(['open', 'closed', 'all'] as const).map((s) => (
            <button key={s} type="button" aria-pressed={scope === s} onClick={() => { setScope(s); setOffset(0) }} className={`px-3 py-1.5 ${scope === s ? 'bg-surface-2 font-medium' : 'hover:bg-surface-2'}`}>{label(s)}</button>
          ))}
        </div>
        <label className="sr-only" htmlFor="sev">Severity</label>
        <select id="sev" value={severity} onChange={(e) => { setSeverity(e.target.value); setOffset(0) }} className={`${input} max-w-[10rem]`}>
          <option value="">Any severity</option>
          {['critical', 'high', 'medium', 'low'].map((s) => <option key={s} value={s}>{label(s)}</option>)}
        </select>
        <label className="sr-only" htmlFor="iq">Search issues</label>
        <input id="iq" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0) }} placeholder="Search title or key" className={`${input} max-w-xs`} />
      </div>
      {list.isLoading && <LoadingBlock label="Loading issues" />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data && list.data.total === 0 && <EmptyState title={scope === 'open' ? 'No open issues' : 'No issues match'}>Issues are opened from an asset page, or from a suggestion the rules make after an observation.</EmptyState>}
      {list.data && list.data.total > 0 && (
        <>
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Issues</caption>
              <thead className="border-b border-line text-ink-2"><tr>{['Key', 'Title', 'Asset', 'Severity', 'State', 'Opened'].map((h) => <th key={h} className="p-2 font-medium">{h}</th>)}</tr></thead>
              <tbody>
                {list.data.items.map((i) => (
                  <tr key={i.id} className="border-b border-line last:border-0">
                    <td className="p-2"><Link className="font-medium text-moss hover:underline" to={`/w/${ws}/issues/${i.id}`}>{i.key}</Link></td>
                    <td className="p-2">{i.title}</td>
                    <td className="p-2 text-ink-2">{i.asset_id ? <Link className="hover:underline" to={`/w/${ws}/assets/${i.asset_id}`}>{i.asset_label}</Link> : '—'}</td>
                    <td className="p-2"><SeverityChip severity={i.severity} /></td>
                    <td className="p-2"><StateChip state={i.state} open={i.is_open} /></td>
                    <td className="p-2 text-ink-2">{relative(i.opened_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination total={list.data.total} limit={PAGE} offset={offset} onChange={setOffset} />
        </>
      )}
    </div>
  )
}
