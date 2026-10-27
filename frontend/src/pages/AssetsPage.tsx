import { useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import type { Asset, AssetKind, HealthBand } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { Field, HealthChip, PageHeader, Pagination, btn, btnPrimary, input } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { ProblemError } from '../api/client'
import { useI18n, type TKey } from '../i18n'
import { atLeast } from '../lib/format'
import { useLifecycleTemplate } from '../lib/lifecycle'
import { useAssets, useCreateAsset, useLocations, useSpecies } from '../lib/slice'
import { AssetCard } from '../components/asset/AssetCard'
import { Icon } from '../components/icons'
import { UseMyLocation } from '../components/UseMyLocation'
import { FilterBar, FilterSelect, LedgerTable, SearchField, Segmented, Tag, type LedgerColumn } from '../components/ui'

const PAGE = 25
const KINDS: AssetKind[] = ['tree', 'plant', 'crop_batch', 'shrub', 'other']

function fieldErrors(e: unknown): Record<string, string> {
  if (!(e instanceof ProblemError)) return {}
  return Object.fromEntries(e.fieldErrors.map((f) => [f.loc[f.loc.length - 1], f.msg]))
}

function RegisterAssetForm({ onDone, preset }: { onDone: () => void; preset?: AssetKind }) {
  const { ws, workspace } = useWorkspaceCtx()
  const { t, te } = useI18n()
  const navigate = useNavigate()
  const species = useSpecies(ws)
  const locations = useLocations(ws)
  const create = useCreateAsset(ws)
  const template = useLifecycleTemplate(ws, true)
  const [kind, setKind] = useState<AssetKind>(preset ?? (workspace.mode === 'agricultural_production' ? 'crop_batch' : 'tree'))
  const fe = fieldErrors(create.error)
  const formRef = useRef<HTMLFormElement>(null)
  function fill(lat: number, lon: number) {
    const f = formRef.current
    if (!f) return
    ;(f.elements.namedItem('latitude') as HTMLInputElement).value = String(lat)
    ;(f.elements.namedItem('longitude') as HTMLInputElement).value = String(lon)
  }

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const text = (k: string) => String(f.get(k) ?? '').trim()
    const num = (k: string) => (text(k) === '' ? undefined : Number(text(k)))
    const body: Record<string, unknown> = {
      label: text('label'), kind, species_id: text('species_id') || undefined, location_id: text('location_id') || undefined,
      tag_code: text('tag_code') || undefined, planted_at: text('planted_at') || undefined, notes: text('notes') || undefined,
    }
    // Only send a starting stage when it is not the default, so the server's default stays the single source of truth.
    if (text('stage') && text('stage') !== 'planted') body.stage = text('stage')
    if (kind === 'crop_batch') {
      body.tracking_mode = 'population'
      body.estimated_count = num('estimated_count')
    }
    if (text('latitude') || text('longitude')) {
      body.latitude = num('latitude')
      body.longitude = num('longitude')
    }
    create.mutate(body, { onSuccess: (a) => navigate(`/w/${ws}/assets/${a.id}`) })
  }

  return (
    <form ref={formRef} onSubmit={submit} className="mb-6 space-y-3 rounded-lg border border-line bg-surface p-4" aria-label={t('assets.register')}>
      <h2 className="font-semibold">{t('assets.registerTitle')}</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field id="label" label={t('assets.field.label')}>
          <input id="label" name="label" required maxLength={200} className={input} placeholder={t('assets.field.labelPlaceholder')} aria-invalid={!!fe.label} />
          {fe.label && <p className="mt-1 text-sm text-critical">{fe.label}</p>}
        </Field>
        <Field id="kind" label={t('assets.field.kind')}>
          <select id="kind" value={kind} onChange={(e) => setKind(e.target.value as AssetKind)} className={input}>
            {KINDS.map((k) => (
              <option key={k} value={k}>{te('kind', k)}</option>
            ))}
          </select>
        </Field>
        <Field id="species_id" label={t('assets.field.species')}>
          <select id="species_id" name="species_id" className={input} defaultValue="">
            <option value="">{t('assets.field.speciesNone')}</option>
            {species.data?.items.map((s) => (
              <option key={s.id} value={s.id}>{s.common_name}</option>
            ))}
          </select>
        </Field>
        <Field id="location_id" label={t(`vocab.location.${workspace.mode}` as TKey)}>
          <select id="location_id" name="location_id" className={input} defaultValue="">
            <option value="">{t('assets.field.locationNone')}</option>
            {locations.data?.items.map((l) => (
              <option key={l.id} value={l.id}>{l.name}</option>
            ))}
          </select>
        </Field>
        <Field id="tag_code" label={t('assets.field.tag')}>
          <input id="tag_code" name="tag_code" maxLength={100} className={input} />
          {fe.tag_code && <p className="mt-1 text-sm text-critical">{fe.tag_code}</p>}
        </Field>
        <Field id="stage" label={t('assets.field.stage')} hint={t('assets.field.stageHint')}>
          <select id="stage" name="stage" className={input} defaultValue="planted">
            {(template.data?.stages ?? [{ key: 'planted', label: 'Planted' }]).map((s) => <option key={s.key} value={s.key}>{te('stage', s.key, s.label)}</option>)}
          </select>
        </Field>
        <Field id="planted_at" label={t('assets.field.planted')}>
          <input id="planted_at" name="planted_at" type="date" className={input} />
        </Field>
        {kind === 'crop_batch' && (
          <Field id="estimated_count" label={t('assets.field.count')} hint={t('assets.field.countHint')}>
            <input id="estimated_count" name="estimated_count" type="number" min={1} required className={input} />
          </Field>
        )}
        <Field id="latitude" label={t('assets.field.lat')}>
          <input id="latitude" name="latitude" inputMode="decimal" className={input} placeholder={t('assets.field.latPlaceholder')} />
        </Field>
        <Field id="longitude" label={t('assets.field.lon')}>
          <input id="longitude" name="longitude" inputMode="decimal" className={input} placeholder={t('assets.field.lonPlaceholder')} />
        </Field>
        <div className="flex flex-col justify-end gap-1 sm:col-span-2 lg:col-span-1">
          <UseMyLocation onLocated={fill} />
          <p className="text-xs text-ink-2">{t('geo.assetHint')}</p>
        </div>
      </div>
      <Field id="notes" label={t('assets.field.notes')}>
        <textarea id="notes" name="notes" rows={2} maxLength={5000} className={input} />
      </Field>
      {create.error != null && Object.keys(fe).length === 0 && <p role="alert" className="text-sm text-critical">{errorMessage(create.error)}</p>}
      <div className="flex gap-2">
        <button className={btnPrimary} disabled={create.isPending}>{create.isPending ? t('assets.registering') : t('assets.register')}</button>
        <button type="button" className={btn} onClick={onDone}>{t('assets.cancel')}</button>
      </div>
    </form>
  )
}

/**
 * The asset registry. With `only`, it is a view of one kind (Trees, Plants, Crop batches): the same list, filters and
 * registration, with the kind fixed. These views are filters of one model, not separate registers (ADR-006).
 */
export function AssetsPage({ only }: { only?: AssetKind } = {}) {
  const { ws, workspace } = useWorkspaceCtx()
  const { t, te, fmt } = useI18n()
  const [adding, setAdding] = useState(false)
  const [q, setQ] = useState('')
  const [chosenKind, setKind] = useState('')
  const kind = only ?? chosenKind
  const [params, setParams] = useSearchParams()
  const speciesId = params.get('species') ?? undefined
  const locationId = params.get('location') ?? undefined
  const locations = useLocations(ws)
  const locationName = locations.data?.items.find((l) => l.id === locationId)?.name
  const species = useSpecies(ws)
  const speciesName = species.data?.items.find((s) => s.id === speciesId)?.common_name
  const [band, setBand] = useState('')
  const [lifecycle, setLifecycle] = useState('active')
  const [offset, setOffset] = useState(0)
  // Photo cards only on the kind tabs (Trees, Plants, Crop batches); "All" is always the ledger table (ADR-073).
  const [view, setView] = useState<'cards' | 'table'>('cards')
  const cards = !!only && view === 'cards'
  const list = useAssets(ws, {
    q, kind: kind || undefined, health_band: (band as HealthBand) || undefined, species_id: speciesId, location_id: locationId, limit: PAGE, offset,
    active: lifecycle === 'all' ? undefined : lifecycle === 'active',
  })
  const canRegister = atLeast(workspace.role, 'worker')
  const viewName = only ? t(`assets.view.${only}` as TKey) : t('assets.title')
  function filter(set: (v: string) => void) {
    return (v: string) => {
      set(v)
      setOffset(0)
    }
  }

  const columns: LedgerColumn<Asset>[] = [
    {
      key: 'asset', header: t('assets.col.asset'), primary: true,
      cell: (a) => (
        <span className="flex flex-wrap items-center gap-2">
          <Link className="font-semibold text-ink hover:text-moss hover:underline" to={`/w/${ws}/assets/${a.id}`}>{a.label}</Link>
          {a.tag_code && <Tag>{a.tag_code}</Tag>}
        </span>
      ),
    },
    { key: 'health', header: t('assets.col.health'), cell: (a) => <HealthChip band={a.state.health_band} score={a.state.health_score} /> },
    {
      key: 'stage', header: t('assets.col.stage'),
      cell: (a) => <span className="text-ink-2">{te('stage', a.current_stage)}{!a.is_active && <span className="ml-1 text-xs text-ink-3">{t('assets.left')}</span>}</span>,
    },
    { key: 'species', header: t('assets.col.species'), cell: (a) => <span className="text-ink-2">{a.species_name ?? '—'}</span> },
    { key: 'where', header: t(`vocab.location.${workspace.mode}` as TKey), cell: (a) => <span className="text-ink-2">{a.location_name ?? '—'}</span> },
    { key: 'seen', header: t('assets.col.lastObserved'), cell: (a) => <span className="text-ink-2">{fmt.relative(a.state.last_observed_at)}</span> },
    {
      key: 'issues', header: t('assets.col.issues'), numeric: true,
      cell: (a) => <span className={a.state.open_issue_count > 0 ? 'font-semibold text-critical' : 'text-ink-3'}>{a.state.open_issue_count}</span>,
    },
    {
      key: 'tasks', header: t('assets.col.tasks'), numeric: true,
      cell: (a) => <span className={a.state.open_task_count > 0 ? 'font-semibold' : 'text-ink-3'}>{a.state.open_task_count}</span>,
    },
  ]

  return (
    <div>
      <PageHeader
        eyebrow={list.data ? t('list.count', { count: list.data.total }) : undefined}
        title={viewName}
        subtitle={only ? t(`assets.viewSubtitle.${only}` as TKey) : t(`assets.subtitle.${workspace.mode}` as TKey, { name: workspace.name })}
      >
        {canRegister && !adding && (
          <button type="button" className={btnPrimary} onClick={() => setAdding(true)}>
            <Icon name="add" size={16} />
            {t('assets.register')}
          </button>
        )}
      </PageHeader>
      {adding && <RegisterAssetForm onDone={() => setAdding(false)} preset={only} />}

      {(speciesId || locationId) && (
        <p className="mb-3 flex items-center gap-2 text-sm">
          {speciesId ? t('assets.speciesFilter', { name: speciesName ?? '…' }) : t('assets.locationFilter', { name: locationName ?? '…' })}
          <button type="button" className={`${btn} px-2 py-0.5 text-xs`} onClick={() => setParams({}, { replace: true })}>{t('assets.clearFilter')}</button>
        </p>
      )}
      <FilterBar label={t('assets.search')}>
        <SearchField id="q" label={t('assets.search')} value={q} onChange={filter(setQ)} placeholder={t('assets.searchPlaceholder')} />
        {!only && (
          <FilterSelect id="kindf" label={t('assets.filterType')} value={kind} onChange={filter(setKind)}>
            <option value="">{t('assets.allTypes')}</option>
            {KINDS.map((k) => <option key={k} value={k}>{te('kind', k)}</option>)}
          </FilterSelect>
        )}
        <FilterSelect id="bandf" label={t('assets.filterHealth')} value={band} onChange={filter(setBand)}>
          <option value="">{t('assets.anyHealth')}</option>
          <option value="healthy">{te('health', 'healthy')}</option>
          <option value="at_risk">{te('health', 'at_risk')}</option>
          <option value="critical">{te('health', 'critical')}</option>
        </FilterSelect>
        <FilterSelect id="lcf" label={t('assets.filterLifecycle')} value={lifecycle} onChange={filter(setLifecycle)}>
          <option value="active">{t('assets.active')}</option>
          <option value="exited">{t('assets.exited')}</option>
          <option value="all">{t('assets.all')}</option>
        </FilterSelect>
        {only && (
          <div className="ml-auto">
            <Segmented label={t('list.view')} value={view} onChange={setView} options={[{ value: 'cards', label: t('list.cards') }, { value: 'table', label: t('list.table') }]} />
          </div>
        )}
      </FilterBar>

      {list.isLoading && <LoadingBlock label={t('assets.loading')} />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data && list.data.total === 0 && (
        <EmptyState
          icon="assets"
          title={q || chosenKind || band || lifecycle !== 'active' ? t('assets.emptyFiltered') : only ? t(`assets.viewEmpty.${only}` as TKey) : t('assets.empty')}
          action={canRegister && !adding ? <button type="button" className={btnPrimary} onClick={() => setAdding(true)}>{t('assets.registerFirst')}</button> : undefined}
        >
          {t('assets.emptyBody')}
        </EmptyState>
      )}
      {list.data && list.data.total > 0 && (
        <>
          {cards ? (
            <ul aria-label={viewName} className="grid grid-cols-1 gap-3 min-[480px]:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {list.data.items.map((a) => <AssetCard key={a.id} ws={ws} asset={a} />)}
            </ul>
          ) : (
            <LedgerTable caption={viewName} columns={columns} rows={list.data.items} rowKey={(a) => a.id} />
          )}
          <Pagination total={list.data.total} limit={PAGE} offset={offset} onChange={setOffset} />
        </>
      )}
    </div>
  )
}
