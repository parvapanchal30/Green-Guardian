import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Issue } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { PageHeader, Pagination, SeverityChip, StateChip } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock } from '../components/states'
import { FilterBar, FilterSelect, LedgerTable, SearchField, Segmented, Tag, type LedgerColumn } from '../components/ui'
import { useI18n, type TKey } from '../i18n'
import { useIssues } from '../lib/slice'

const PAGE = 25
type Scope = 'open' | 'waiting' | 'closed' | 'all'
const SCOPE_PARAMS: Record<Scope, { is_open?: boolean; waiting?: boolean }> = {
  open: { is_open: true, waiting: false },
  waiting: { is_open: true, waiting: true },
  closed: { is_open: false },
  all: {},
}

/**
 * Issues (ADR-073): open ones, those waiting for a check after the work was done, closed ones, or all; most severe
 * first unless the reader asks for the newest.
 */
export function IssuesPage() {
  const { ws } = useWorkspaceCtx()
  const { t, te, fmt } = useI18n()
  const [scope, setScope] = useState<Scope>('open')
  const [severity, setSeverity] = useState('')
  const [sort, setSort] = useState<'severity' | 'recent'>('severity')
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)
  const list = useIssues(ws, { ...SCOPE_PARAMS[scope], severity: severity || undefined, q, sort, limit: PAGE, offset })
  function filter<T>(set: (v: T) => void) {
    return (v: T) => {
      set(v)
      setOffset(0)
    }
  }

  const columns: LedgerColumn<Issue>[] = [
    {
      key: 'title', header: t('issues.col.title'), primary: true,
      cell: (i) => (
        <span className="flex flex-wrap items-center gap-2">
          <Tag>{i.key}</Tag>
          <Link className="font-semibold text-ink hover:text-moss hover:underline" to={`/w/${ws}/issues/${i.id}`}>{i.title}</Link>
        </span>
      ),
    },
    { key: 'severity', header: t('issues.col.severity'), cell: (i) => <SeverityChip severity={i.severity} /> },
    { key: 'asset', header: t('issues.col.asset'), cell: (i) => (i.asset_id ? <Link className="text-moss hover:underline" to={`/w/${ws}/assets/${i.asset_id}`}>{i.asset_label}</Link> : <span className="text-ink-3">—</span>) },
    { key: 'state', header: t('issues.col.state'), cell: (i) => <StateChip state={i.state} open={i.is_open} /> },
    { key: 'opened', header: t('issues.col.opened'), cell: (i) => <span className="text-ink-2">{fmt.relative(i.opened_at)}</span> },
  ]
  const scopes: { value: Scope; label: string }[] = (['open', 'waiting', 'closed', 'all'] as const).map((s) => ({ value: s, label: t(`issues.scope.${s}` as TKey) }))

  return (
    <div>
      <PageHeader eyebrow={list.data ? t('list.count', { count: list.data.total }) : undefined} title={t('issues.title')} subtitle={t('issues.subtitle')} />
      <FilterBar label={t('issues.search')}>
        <Segmented label={t('issues.scope')} value={scope} options={scopes} onChange={filter(setScope)} />
        <SearchField id="iq" label={t('issues.search')} value={q} onChange={filter(setQ)} placeholder={t('issues.searchPlaceholder')} />
        <FilterSelect id="sev" label={t('issues.severity')} value={severity} onChange={filter(setSeverity)}>
          <option value="">{t('issues.anySeverity')}</option>
          {['critical', 'high', 'medium', 'low'].map((s) => <option key={s} value={s}>{te('severity', s)}</option>)}
        </FilterSelect>
        <FilterSelect id="isort" label={t('list.order')} value={sort} onChange={filter((v: string) => setSort(v as 'severity' | 'recent'))}>
          <option value="severity">{t('issues.sort.severity')}</option>
          <option value="recent">{t('issues.sort.recent')}</option>
        </FilterSelect>
      </FilterBar>
      {scope === 'waiting' && <p className="mb-3 text-sm text-ink-2">{t('issues.waitingHint')}</p>}
      {list.isLoading && <LoadingBlock label={t('issues.loading')} />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data && list.data.total === 0 && (
        <EmptyState icon="issues" title={scope === 'open' ? t('issues.noneOpen') : scope === 'waiting' ? t('issues.noneWaiting') : t('issues.noneMatch')}>{t('issues.emptyBody')}</EmptyState>
      )}
      {list.data && list.data.total > 0 && (
        <>
          <LedgerTable caption={t('issues.caption')} columns={columns} rows={list.data.items} rowKey={(i) => i.id} />
          <Pagination total={list.data.total} limit={PAGE} offset={offset} onChange={setOffset} />
        </>
      )}
    </div>
  )
}
