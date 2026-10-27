import { useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import type { LocationItem, LocationKind } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { Field, PageHeader, btn, btnPrimary, input } from '../components/domain'
import { SchedulePanel } from '../components/SchedulePanel'
import { UseMyLocation } from '../components/UseMyLocation'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { StatusChip } from '../components/StatusChip'
import { Icon } from '../components/icons'
import { Tag } from '../components/ui'
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

  const formRef = useRef<HTMLFormElement>(null)
  function here(lat: number, lon: number) {
    const form = formRef.current
    if (!form) return
    ;(form.elements.namedItem('lat') as HTMLInputElement).value = String(lat)
    ;(form.elements.namedItem('lon') as HTMLInputElement).value = String(lon)
  }

  return (
    <form ref={formRef} onSubmit={submit} aria-label={t('loc.addForm')} className="mb-4 grid gap-3 rounded-lg border border-line bg-surface p-3 sm:grid-cols-3">
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
      <div className="flex items-end"><UseMyLocation onLocated={here} /></div>
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
    <li className={`flex flex-col rounded-lg border border-line bg-surface p-4 text-sm ${open ? 'md:col-span-2' : ''}`}>
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <h2 className="text-[19px] leading-snug font-semibold">{l.name}</h2>
          <p className="mt-0.5 flex flex-wrap items-center gap-2 text-[13px] text-ink-2">
            <Tag>{te('locationKind', l.kind)}</Tag>
            {parent && <span>{t('loc.inside', { name: parent })}</span>}
          </p>
        </div>
        {l.needs_attention > 0 && <StatusChip tone="at-risk">{t('loc.attention', { count: l.needs_attention })}</StatusChip>}
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-3 border-t border-line-soft pt-3">
        <div>
          <dt className="font-mono text-[11px] text-ink-3 uppercase">{t('species.assets')}</dt>
          <dd className="mt-0.5">
            {l.assets > 0 ? (
              <Link className="font-semibold text-moss hover:underline" to={`/w/${ws}/assets?location=${l.id}`}>{t('loc.assets', { count: l.assets })}</Link>
            ) : <span className="text-ink-3">{t('loc.assets', { count: 0 })}</span>}
          </dd>
        </div>
        <div>
          <dt className="font-mono text-[11px] text-ink-3 uppercase">{t('loc.coords')}</dt>
          <dd className="mt-0.5 font-mono text-xs text-ink-2">
            {l.latitude != null && l.longitude != null
              ? `${fmt.number(l.latitude, { maximumFractionDigits: 4 })}, ${fmt.number(l.longitude, { maximumFractionDigits: 4 })}`
              : <span className="font-sans text-sm text-ink-3">{t('loc.noCoords')}</span>}
          </dd>
        </div>
      </dl>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1 text-[13px] text-ink-2">
          <Icon name="recurring" size={14} />
          {l.schedules > 0 ? t('loc.schedules', { count: l.schedules }) : t('loc.noSchedules')}
        </span>
        <button type="button" className={`${btn} ml-auto px-2.5 py-1 text-xs`} aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {open ? t('loc.hideInspections') : t('loc.showInspections')}
        </button>
      </div>
      {open && <div className="mt-3 border-t border-line-soft pt-3"><SchedulePanel ws={ws} location={l} role={role} compact /></div>}
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
      <PageHeader eyebrow={list.data ? t('list.count', { count: list.data.items.length }) : undefined} title={t(`loc.title.${workspace.mode}` as TKey)} subtitle={t('loc.subtitle')}>
        {canAdd && !adding && (
          <button type="button" className={btnPrimary} onClick={() => setAdding(true)}>
            <Icon name="add" size={16} />
            {t('loc.add')}
          </button>
        )}
      </PageHeader>
      {adding && <AddForm ws={ws} onDone={() => setAdding(false)} />}
      {list.isLoading && <LoadingBlock label={t('loc.loading')} />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data && list.data.items.length === 0 && <EmptyState icon="zones" title={t('loc.none')}>{t('loc.noneBody')}</EmptyState>}
      <ul className="grid gap-3 md:grid-cols-2">
        {list.data?.items.map((l) => <Row key={l.id} ws={ws} l={l} parent={l.parent_id ? names.get(l.parent_id) : undefined} role={workspace.role} />)}
      </ul>
      <p className="mt-3 text-xs text-ink-3">{t('loc.countsNote')}</p>
    </div>
  )
}
