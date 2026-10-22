import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { AssetKind, HealthBand } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { Field, HealthChip, PageHeader, Pagination, btn, btnPrimary, input } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { ProblemError } from '../api/client'
import { useI18n, type TKey } from '../i18n'
import { atLeast } from '../lib/format'
import { useLifecycleTemplate } from '../lib/lifecycle'
import { useAssets, useCreateAsset, useCreateLocation, useLocations, useSpecies } from '../lib/slice'

const PAGE = 25
const KINDS: AssetKind[] = ['tree', 'plant', 'crop_batch', 'shrub', 'other']

function fieldErrors(e: unknown): Record<string, string> {
  if (!(e instanceof ProblemError)) return {}
  return Object.fromEntries(e.fieldErrors.map((f) => [f.loc[f.loc.length - 1], f.msg]))
}

function RegisterAssetForm({ onDone }: { onDone: () => void }) {
  const { ws, workspace } = useWorkspaceCtx()
  const { t, te } = useI18n()
  const navigate = useNavigate()
  const species = useSpecies(ws)
  const locations = useLocations(ws)
  const create = useCreateAsset(ws)
  const template = useLifecycleTemplate(ws, true)
  const [kind, setKind] = useState<AssetKind>(workspace.mode === 'agricultural_production' ? 'crop_batch' : 'tree')
  const fe = fieldErrors(create.error)

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
    <form onSubmit={submit} className="mb-6 space-y-3 rounded-lg border border-line bg-surface p-4" aria-label={t('assets.register')}>
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

function AddLocation() {
  const { ws, workspace } = useWorkspaceCtx()
  const t = useI18n().t
  const create = useCreateLocation(ws)
  const kind = workspace.mode === 'agricultural_production' ? 'field' : 'zone'
  return (
    <form
      className="mb-4 flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        const input_ = e.currentTarget.elements.namedItem('loc') as HTMLInputElement
        create.mutate({ name: input_.value.trim(), kind }, { onSuccess: () => (input_.value = '') })
      }}
    >
      <Field id="loc" label={t(`assets.newLocation.${workspace.mode}` as TKey)}>
        <input id="loc" name="loc" required maxLength={200} className={input} placeholder={t(`assets.locationPlaceholder.${workspace.mode}` as TKey)} />
      </Field>
      <button className={btn} disabled={create.isPending}>{t(`assets.addLocation.${workspace.mode}` as TKey)}</button>
      {create.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(create.error)}</p>}
    </form>
  )
}

export function AssetsPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const { t, te, fmt } = useI18n()
  const [adding, setAdding] = useState(false)
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('')
  const [band, setBand] = useState('')
  const [lifecycle, setLifecycle] = useState('active')
  const [offset, setOffset] = useState(0)
  const list = useAssets(ws, {
    q, kind: kind || undefined, health_band: (band as HealthBand) || undefined, limit: PAGE, offset,
    active: lifecycle === 'all' ? undefined : lifecycle === 'active',
  })
  const canRegister = atLeast(workspace.role, 'worker')

  return (
    <div>
      <PageHeader title={t('assets.title')} subtitle={t(`assets.subtitle.${workspace.mode}` as TKey, { name: workspace.name })}>
        {canRegister && !adding && <button type="button" className={btnPrimary} onClick={() => setAdding(true)}>{t('assets.register')}</button>}
      </PageHeader>
      {adding && <RegisterAssetForm onDone={() => setAdding(false)} />}
      {atLeast(workspace.role, 'manager') && <AddLocation />}

      <div className="mb-3 flex flex-wrap gap-2" role="search">
        <label className="sr-only" htmlFor="q">{t('assets.search')}</label>
        <input id="q" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0) }} placeholder={t('assets.searchPlaceholder')} className={`${input} max-w-xs`} />
        <label className="sr-only" htmlFor="kindf">{t('assets.filterType')}</label>
        <select id="kindf" value={kind} onChange={(e) => { setKind(e.target.value); setOffset(0) }} className={`${input} max-w-[10rem]`}>
          <option value="">{t('assets.allTypes')}</option>
          {KINDS.map((k) => <option key={k} value={k}>{te('kind', k)}</option>)}
        </select>
        <label className="sr-only" htmlFor="bandf">{t('assets.filterHealth')}</label>
        <select id="bandf" value={band} onChange={(e) => { setBand(e.target.value); setOffset(0) }} className={`${input} max-w-[10rem]`}>
          <option value="">{t('assets.anyHealth')}</option>
          <option value="healthy">{te('health', 'healthy')}</option>
          <option value="at_risk">{te('health', 'at_risk')}</option>
          <option value="critical">{te('health', 'critical')}</option>
        </select>
        <label className="sr-only" htmlFor="lcf">{t('assets.filterLifecycle')}</label>
        <select id="lcf" value={lifecycle} onChange={(e) => { setLifecycle(e.target.value); setOffset(0) }} className={`${input} max-w-[12rem]`}>
          <option value="active">{t('assets.active')}</option>
          <option value="exited">{t('assets.exited')}</option>
          <option value="all">{t('assets.all')}</option>
        </select>
      </div>

      {list.isLoading && <LoadingBlock label={t('assets.loading')} />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data && list.data.total === 0 && (
        <EmptyState title={q || kind || band || lifecycle !== 'active' ? t('assets.emptyFiltered') : t('assets.empty')} action={canRegister && !adding ? <button type="button" className={btnPrimary} onClick={() => setAdding(true)}>{t('assets.registerFirst')}</button> : undefined}>
          {t('assets.emptyBody')}
        </EmptyState>
      )}
      {list.data && list.data.total > 0 && (
        <>
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">{t('assets.title')}</caption>
              <thead className="border-b border-line text-ink-2">
                <tr>
                  <th className="p-2 font-medium">{t('assets.col.asset')}</th><th className="p-2 font-medium">{t('assets.col.stage')}</th><th className="p-2 font-medium">{t('assets.col.species')}</th>
                  <th className="p-2 font-medium">{t(`vocab.location.${workspace.mode}` as TKey)}</th><th className="p-2 font-medium">{t('assets.col.health')}</th>
                  <th className="p-2 font-medium">{t('assets.col.lastObserved')}</th><th className="p-2 font-medium">{t('assets.col.issues')}</th><th className="p-2 font-medium">{t('assets.col.tasks')}</th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((a) => (
                  <tr key={a.id} className="border-b border-line last:border-0">
                    <td className="p-2"><Link className="font-medium text-moss hover:underline" to={`/w/${ws}/assets/${a.id}`}>{a.label}</Link>{a.tag_code && <span className="ml-2 text-xs text-ink-3">{a.tag_code}</span>}</td>
                    <td className="p-2 text-ink-2">{te('stage', a.current_stage)}{!a.is_active && <span className="ml-1 text-xs text-ink-3">{t('assets.left')}</span>}</td>
                    <td className="p-2 text-ink-2">{a.species_name ?? '—'}</td>
                    <td className="p-2 text-ink-2">{a.location_name ?? '—'}</td>
                    <td className="p-2"><HealthChip band={a.state.health_band} score={a.state.health_score} /></td>
                    <td className="p-2 text-ink-2">{fmt.relative(a.state.last_observed_at)}</td>
                    <td className="p-2">{a.state.open_issue_count}</td>
                    <td className="p-2">{a.state.open_task_count}</td>
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
