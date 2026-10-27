import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Page, SpeciesItem } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { Field, PageHeader, btn, btnPrimary, input } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { Icon } from '../components/icons'
import { FilterBar, FilterSelect, LedgerTable, SearchField, Segmented, Tag, type LedgerColumn } from '../components/ui'
import { useI18n } from '../i18n'
import { atLeast } from '../lib/format'
import { qs, useCreateSpecies } from '../lib/slice'

const CATEGORIES = ['tree', 'crop', 'plant', 'ornamental', 'other'] as const

const useSpeciesUsage = (ws: string, params: { category?: string; q?: string; mine?: boolean }) =>
  useQuery({
    queryKey: [ws, 'species', 'usage', params],
    queryFn: () => api<Page<SpeciesItem>>(`/workspaces/${ws}/species${qs({ ...params, limit: 200 })}`),
  })

function AddSpecies({ ws, crops, onDone }: { ws: string; crops: boolean; onDone: () => void }) {
  const { t, te } = useI18n()
  const create = useCreateSpecies(ws)
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const text = (k: string) => String(f.get(k) ?? '').trim()
    create.mutate({ category: text('category'), common_name: text('name'), scientific_name: text('scientific') || undefined }, { onSuccess: onDone })
  }
  return (
    <form onSubmit={submit} aria-label={t('species.addForm')} className="mb-4 grid gap-3 rounded-lg border border-line bg-surface p-3 sm:grid-cols-3">
      <Field id="sp-name" label={t('species.name')}><input id="sp-name" name="name" className={input} required maxLength={200} /></Field>
      <Field id="sp-sci" label={t('species.scientific')}><input id="sp-sci" name="scientific" className={input} maxLength={200} /></Field>
      <Field id="sp-cat" label={t('species.category')}>
        <select id="sp-cat" name="category" className={input} defaultValue={crops ? 'crop' : 'tree'}>
          {CATEGORIES.map((c) => <option key={c} value={c}>{te('speciesCategory', c)}</option>)}
        </select>
      </Field>
      {create.error != null && <p role="alert" className="text-sm text-critical sm:col-span-3">{errorMessage(create.error)}</p>}
      <div className="flex gap-2 sm:col-span-3">
        <button className={btnPrimary} disabled={create.isPending}>{t('species.save')}</button>
        <button type="button" className={btn} onClick={onDone}>{t('issue.cancel')}</button>
      </div>
    </form>
  )
}

/**
 * The species catalog (global seed plus this workspace's own), with how many live assets of THIS workspace use each.
 * `crops` is the Crops view: crop species only, those actually grown here first, with batch and plant counts.
 */
export function SpeciesPage({ crops = false }: { crops?: boolean } = {}) {
  const { ws, workspace } = useWorkspaceCtx()
  const { t, te, fmt } = useI18n()
  const [q, setQ] = useState('')
  const [category, setCategory] = useState('')
  const [adding, setAdding] = useState(false)
  // This workspace's species (used here or added here) by default; the shared catalog on request (ADR-078).
  const [scope, setScope] = useState<'mine' | 'catalog'>('mine')
  const mine = scope === 'mine'
  const list = useSpeciesUsage(ws, { category: crops ? 'crop' : category || undefined, q: q || undefined, mine: mine || undefined })
  const canAdd = atLeast(workspace.role, 'manager')
  const title = crops ? t('species.cropsTitle') : t('species.title')

  const count = (n: number, s: SpeciesItem) =>
    n > 0 ? <Link className="font-semibold text-moss hover:underline" to={`/w/${ws}/assets?species=${s.id}`}>{fmt.number(n)}</Link> : <span className="text-ink-3">0</span>
  const columns: LedgerColumn<SpeciesItem>[] = [
    {
      key: 'name', header: t('species.name'), primary: true,
      cell: (s) => (
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-semibold">{s.common_name}</span>
          {!s.is_global && <Tag tone="moss">{t('species.own')}</Tag>}
        </span>
      ),
    },
    { key: 'sci', header: t('species.scientific'), cell: (s) => <span className="text-ink-2 italic">{s.scientific_name ?? '—'}</span> },
    ...(crops ? [] : [{ key: 'cat', header: t('species.category'), cell: (s: SpeciesItem) => te('speciesCategory', s.category) }]),
    { key: 'assets', header: crops ? t('species.batches') : t('species.assets'), numeric: true, cell: (s) => count(s.assets, s) },
    ...(crops
      ? [{ key: 'plants', header: t('species.plants'), numeric: true, cell: (s: SpeciesItem) => (s.plants != null ? fmt.number(s.plants) : <span className="text-ink-3">—</span>) }]
      : []),
  ]

  return (
    <div>
      <PageHeader eyebrow={list.data ? t('list.count', { count: list.data.items.length }) : undefined} title={title} subtitle={crops ? t('species.cropsSubtitle') : t('species.subtitle')}>
        {canAdd && !adding && (
          <button type="button" className={btn} onClick={() => setAdding(true)}>
            <Icon name="add" size={16} />
            {t('species.add')}
          </button>
        )}
      </PageHeader>
      {adding && <AddSpecies ws={ws} crops={crops} onDone={() => setAdding(false)} />}
      <FilterBar label={t('species.search')}>
        <SearchField id="sp-q" label={t('species.search')} value={q} onChange={setQ} placeholder={t('species.searchPlaceholder')} />
        {!crops && (
          <FilterSelect id="sp-catf" label={t('species.category')} value={category} onChange={setCategory}>
            <option value="">{t('species.allCategories')}</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{te('speciesCategory', c)}</option>)}
          </FilterSelect>
        )}
        <Segmented label={t('species.scope')} value={scope} onChange={setScope} options={[{ value: 'mine', label: t('species.scope.mine') }, { value: 'catalog', label: t('species.scope.catalog') }]} />
      </FilterBar>
      {list.isLoading && <LoadingBlock label={t('species.loading')} />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data && list.data.items.length === 0 && (
        <EmptyState icon="species" title={mine && !q && !category ? (crops ? t('species.noCrops') : t('species.noneUsed')) : t('species.none')}>{mine ? t('species.noneUsedBody') : t('species.noneBody')}</EmptyState>
      )}
      {list.data && list.data.items.length > 0 && <LedgerTable caption={title} columns={columns} rows={list.data.items} rowKey={(s) => s.id} />}
      <p className="mt-3 text-xs text-ink-3">{mine ? t('species.mineNote') : t('species.catalogNote')} {t('species.countsNote')}</p>
    </div>
  )
}
