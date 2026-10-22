import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { PageHeader, Pagination, SeverityChip, StateChip, input } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock } from '../components/states'
import { useI18n, type TKey } from '../i18n'
import { useIssues } from '../lib/slice'

const PAGE = 25
const COLUMNS = ['key', 'title', 'asset', 'severity', 'state', 'opened'] as const

export function IssuesPage() {
  const { ws } = useWorkspaceCtx()
  const { t, te, fmt } = useI18n()
  const [scope, setScope] = useState<'open' | 'closed' | 'all'>('open')
  const [severity, setSeverity] = useState('')
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)
  const list = useIssues(ws, { is_open: scope === 'all' ? undefined : scope === 'open', severity: severity || undefined, q, limit: PAGE, offset })

  return (
    <div>
      <PageHeader title={t('issues.title')} subtitle={t('issues.subtitle')} />
      <div className="mb-3 flex flex-wrap items-center gap-2" role="search">
        <div role="group" aria-label={t('issues.scope')} className="flex overflow-hidden rounded border border-line text-sm">
          {(['open', 'closed', 'all'] as const).map((s) => (
            <button key={s} type="button" aria-pressed={scope === s} onClick={() => { setScope(s); setOffset(0) }} className={`px-3 py-1.5 ${scope === s ? 'bg-surface-2 font-medium' : 'hover:bg-surface-2'}`}>{t(`issues.scope.${s}` as TKey)}</button>
          ))}
        </div>
        <label className="sr-only" htmlFor="sev">{t('issues.severity')}</label>
        <select id="sev" value={severity} onChange={(e) => { setSeverity(e.target.value); setOffset(0) }} className={`${input} max-w-[10rem]`}>
          <option value="">{t('issues.anySeverity')}</option>
          {['critical', 'high', 'medium', 'low'].map((s) => <option key={s} value={s}>{te('severity', s)}</option>)}
        </select>
        <label className="sr-only" htmlFor="iq">{t('issues.search')}</label>
        <input id="iq" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0) }} placeholder={t('issues.searchPlaceholder')} className={`${input} max-w-xs`} />
      </div>
      {list.isLoading && <LoadingBlock label={t('issues.loading')} />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data && list.data.total === 0 && <EmptyState title={scope === 'open' ? t('issues.noneOpen') : t('issues.noneMatch')}>{t('issues.emptyBody')}</EmptyState>}
      {list.data && list.data.total > 0 && (
        <>
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">{t('issues.caption')}</caption>
              <thead className="border-b border-line text-ink-2"><tr>{COLUMNS.map((h) => <th key={h} className="p-2 font-medium">{t(`issues.col.${h}` as TKey)}</th>)}</tr></thead>
              <tbody>
                {list.data.items.map((i) => (
                  <tr key={i.id} className="border-b border-line last:border-0">
                    <td className="p-2"><Link className="font-medium text-moss hover:underline" to={`/w/${ws}/issues/${i.id}`}>{i.key}</Link></td>
                    <td className="p-2">{i.title}</td>
                    <td className="p-2 text-ink-2">{i.asset_id ? <Link className="hover:underline" to={`/w/${ws}/assets/${i.asset_id}`}>{i.asset_label}</Link> : '—'}</td>
                    <td className="p-2"><SeverityChip severity={i.severity} /></td>
                    <td className="p-2"><StateChip state={i.state} open={i.is_open} /></td>
                    <td className="p-2 text-ink-2">{fmt.relative(i.opened_at)}</td>
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
