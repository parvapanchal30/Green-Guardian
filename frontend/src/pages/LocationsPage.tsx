import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import type { LocationItem, LocationKind } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { Field, PageHeader, btn, btnPrimary, input } from '../components/domain'
import { SchedulePanel } from '../components/SchedulePanel'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { StatusChip } from '../components/StatusChip'
import { useI18n, type TKey } from '../i18n'
import { atLeast } from '../lib/format'
import { useCreateLocation, useLocations } from '../lib/slice'

const KINDS: LocationKind[] = ['site', 'field', 'zone', 'plot']

function AddForm({ ws, onDone }: { ws: string; onDone: () => void }) {
  const { t, te } = useI18n()
  const { workspace } = useWorkspaceCtx()
  const create = useCreateLocation(ws)
  const locations = useLocations(ws)
  const [problem, setProblem] = useState<string | null>(null)

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const text = (k: string) => String(f.get(k) ?? '').trim()
    const lat = text('lat')
    const lon = text('lon')
    if ((lat === '') !== (lon === '')) return setProblem(t('loc.errBoth'))
    const la = Number(lat)
    const lo = Number(lon)
    if (lat !== '' && (!Number.isFinite(la) || la < -90 || la > 90 || !Number.isFinite(lo) || lo < -180 || lo > 180)) return setProblem(t('loc.errRange'))
    setProblem(null)
    create.mutate(
      {
        name: text('name'),
        kind: text('kind'),
        parent_id: text('parent') || undefined,
        latitude: lat === '' ? undefined : la,
        longitude: lon === '' ? undefined : lo,
      },
      { onSuccess: onDone },
    )
  }

  function here(form: HTMLFormElement | null) {
    navigator.geolocation?.getCurrentPosition((p) => {
      if (!form) return
      ;(form.elements.namedItem('lat') as HTMLInputElement).value = p.coords.latitude.toFixed(5)
      ;(form.elements.namedItem('lon') as HTMLInputElement).value = p.coords.longitude.toFixed(5)
    })
  }

  return (
    <form onSubmit={submit} aria-label={t('loc.addForm')} className="mb-4 grid gap-3 rounded-lg border border-line bg-surface p-3 sm:grid-cols-3">
      <Field id="loc-name" label={t('loc.name')}><input id="loc-name" name="name" className={input} required maxLength={200} /></Field>
      <Field id="loc-kind" label={t('loc.kind')}>
        <select id="loc-kind" name="kind" className={input} defaultValue={workspace.mode === 'agricultural_production' ? 'field' : 'zone'}>
          {KINDS.map((k) => <option key={k} value={k}>{te('locationKind', k)}</option>)}
        </select>
      </Field>
      <Field id="loc-parent" label={t('loc.parent')}>
        <select id="loc-parent" name="parent" className={input} defaultValue="">
          <option value="">{t('loc.noParent')}</option>
          {locations.data?.items.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
      </Field>
      <Field id="loc-lat" label={t('weather.latitude')}><input id="loc-lat" name="lat" inputMode="decimal" className={input} /></Field>
      <Field id="loc-lon" label={t('weather.longitude')}><input id="loc-lon" name="lon" inputMode="decimal" className={input} /></Field>
      <div className="flex items-end"><button type="button" className={btn} onClick={(e) => here(e.currentTarget.form)}>{t('weather.myLocation')}</button></div>
      {(problem || create.error != null) && <p role="alert" className="text-sm text-critical sm:col-span-3">{problem ?? errorMessage(create.error)}</p>}
      <div className="flex gap-2 sm:col-span-3">
        <button className={btnPrimary} disabled={create.isPending}>{t('loc.save')}</button>
        <button type="button" className={btn} onClick={onDone}>{t('issue.cancel')}</button>
      </div>
    </form>
  )
}

function Row({ ws, l, parent, role }: { ws: string; l: LocationItem; parent: string | undefined; role: Parameters<typeof SchedulePanel>[0]['role'] }) {
  const { t, te, fmt } = useI18n()
  const [open, setOpen] = useState(false)
  return (
    <li className="rounded-lg border border-line bg-surface p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{l.name}</span>
        <StatusChip tone="neutral">{te('locationKind', l.kind)}</StatusChip>
        {parent && <span className="text-ink-3">{t('loc.inside', { name: parent })}</span>}
        {l.assets > 0 ? (
          <Link className="text-moss hover:underline" to={`/w/${ws}/assets?location=${l.id}`}>{t('loc.assets', { count: l.assets })}</Link>
        ) : <span className="text-ink-3">{t('loc.assets', { count: 0 })}</span>}
        {l.needs_attention > 0 && <StatusChip tone="at-risk">{t('loc.attention', { count: l.needs_attention })}</StatusChip>}
        {l.schedules > 0 && <StatusChip tone="building">{t('loc.schedules', { count: l.schedules })}</StatusChip>}
        {l.latitude != null && l.longitude != null
          ? <span className="text-xs text-ink-3">{fmt.number(l.latitude, { maximumFractionDigits: 4 })}, {fmt.number(l.longitude, { maximumFractionDigits: 4 })}</span>
          : <span className="text-xs text-ink-3">{t('loc.noCoords')}</span>}
        <button type="button" className={`${btn} ml-auto px-2 py-0.5 text-xs`} aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {open ? t('loc.hideInspections') : t('loc.showInspections')}
        </button>
      </div>
      {open && <div className="mt-3"><SchedulePanel ws={ws} location={l} role={role} compact /></div>}
    </li>
  )
}

/** Fields and zones: the spatial structure of the workspace, what is placed where, and recurring checks per place. */
export function LocationsPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const { t } = useI18n()
  const list = useLocations(ws)
  const [adding, setAdding] = useState(false)
  const canAdd = atLeast(workspace.role, 'manager')
  const names = new Map(list.data?.items.map((l) => [l.id, l.name]))

  return (
    <div>
      <PageHeader title={t(`loc.title.${workspace.mode}` as TKey)} subtitle={t('loc.subtitle')}>
        {canAdd && !adding && <button type="button" className={btnPrimary} onClick={() => setAdding(true)}>{t('loc.add')}</button>}
      </PageHeader>
      {adding && <AddForm ws={ws} onDone={() => setAdding(false)} />}
      {list.isLoading && <LoadingBlock label={t('loc.loading')} />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data && list.data.items.length === 0 && <EmptyState title={t('loc.none')}>{t('loc.noneBody')}</EmptyState>}
      <ul className="space-y-2">
        {list.data?.items.map((l) => <Row key={l.id} ws={ws} l={l} parent={l.parent_id ? names.get(l.parent_id) : undefined} role={workspace.role} />)}
      </ul>
      <p className="mt-2 text-xs text-ink-3">{t('loc.countsNote')}</p>
    </div>
  )
}
