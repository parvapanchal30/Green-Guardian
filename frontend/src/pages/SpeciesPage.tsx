import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Page, SpeciesItem } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { Field, PageHeader, btn, btnPrimary, input } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { StatusChip } from '../components/StatusChip'
import { useI18n } from '../i18n'
import { atLeast } from '../lib/format'
import { qs, useCreateSpecies } from '../lib/slice'

const CATEGORIES = ['tree', 'crop', 'plant', 'ornamental', 'other'] as const

const useSpeciesUsage = (ws: string, params: { category?: string; q?: string; in_use?: boolean }) =>
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
  const [usedOnly, setUsedOnly] = useState(crops)
  const [adding, setAdding] = useState(false)
  const list = useSpeciesUsage(ws, { category: crops ? 'crop' : category || undefined, q: q || undefined, in_use: usedOnly || undefined })
  const canAdd = atLeast(workspace.role, 'manager')

  return (
    <div>
      <PageHeader title={crops ? t('species.cropsTitle') : t('species.title')} subtitle={crops ? t('species.cropsSubtitle') : t('species.subtitle')}>
        {canAdd && !adding && <button type="button" className={btn} onClick={() => setAdding(true)}>{t('species.add')}</button>}
      </PageHeader>
      {adding && <AddSpecies ws={ws} crops={crops} onDone={() => setAdding(false)} />}
      <div className="mb-3 flex flex-wrap items-center gap-2" role="search">
        <label className="sr-only" htmlFor="sp-q">{t('species.search')}</label>
        <input id="sp-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('species.searchPlaceholder')} className={`${input} max-w-xs`} />
        {!crops && (
          <>
            <label className="sr-only" htmlFor="sp-catf">{t('species.category')}</label>
            <select id="sp-catf" value={category} onChange={(e) => setCategory(e.target.value)} className={`${input} max-w-[10rem]`}>
              <option value="">{t('species.allCategories')}</option>
              {CATEGORIES.map((c) => <option key={c} value={c}>{te('speciesCategory', c)}</option>)}
            </select>
          </>
        )}
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={usedOnly} onChange={(e) => setUsedOnly(e.target.checked)} /> {t('species.usedOnly')}</label>
      </div>
      {list.isLoading && <LoadingBlock label={t('species.loading')} />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data && list.data.items.length === 0 && (
        <EmptyState title={usedOnly ? (crops ? t('species.noCrops') : t('species.noneUsed')) : t('species.none')}>{usedOnly ? t('species.noneUsedBody') : t('species.noneBody')}</EmptyState>
      )}
      {list.data && list.data.items.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">{crops ? t('species.cropsTitle') : t('species.title')}</caption>
            <thead className="border-b border-line text-ink-2">
              <tr>
                <th className="p-2 font-medium">{t('species.name')}</th>
                <th className="p-2 font-medium">{t('species.scientific')}</th>
                {!crops && <th className="p-2 font-medium">{t('species.category')}</th>}
                <th className="p-2 font-medium">{crops ? t('species.batches') : t('species.assets')}</th>
                {crops && <th className="p-2 font-medium">{t('species.plants')}</th>}
              </tr>
            </thead>
            <tbody>
              {list.data.items.map((s) => (
                <tr key={s.id} className="border-b border-line last:border-0">
                  <td className="p-2">
                    <span className="font-medium">{s.common_name}</span>{' '}
                    {!s.is_global && <StatusChip tone="neutral">{t('species.own')}</StatusChip>}
                  </td>
                  <td className="p-2 italic text-ink-2">{s.scientific_name ?? '—'}</td>
                  {!crops && <td className="p-2">{te('speciesCategory', s.category)}</td>}
                  <td className="p-2">
                    {s.assets > 0 ? <Link className="text-moss hover:underline" to={`/w/${ws}/assets?species=${s.id}`}>{fmt.number(s.assets)}</Link> : <span className="text-ink-3">0</span>}
                  </td>
                  {crops && <td className="p-2">{s.plants != null ? fmt.number(s.plants) : <span className="text-ink-3">—</span>}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-xs text-ink-3">{t('species.countsNote')}</p>
    </div>
  )
}
