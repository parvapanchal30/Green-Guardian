import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { AssetKind, HealthBand } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { Field, HealthChip, PageHeader, Pagination, btn, btnPrimary, input } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { ProblemError } from '../api/client'
import { atLeast, label, relative } from '../lib/format'
import { useAssets, useCreateAsset, useCreateLocation, useLocations, useSpecies } from '../lib/slice'
import { VOCABULARY } from '../lib/vocabulary'

const PAGE = 25
const KINDS: AssetKind[] = ['tree', 'plant', 'crop_batch', 'shrub', 'other']

function fieldErrors(e: unknown): Record<string, string> {
  if (!(e instanceof ProblemError)) return {}
  return Object.fromEntries(e.fieldErrors.map((f) => [f.loc[f.loc.length - 1], f.msg]))
}

function RegisterAssetForm({ onDone }: { onDone: () => void }) {
  const { ws, workspace } = useWorkspaceCtx()
  const vocab = VOCABULARY[workspace.mode]
  const navigate = useNavigate()
  const species = useSpecies(ws)
  const locations = useLocations(ws)
  const create = useCreateAsset(ws)
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
    <form onSubmit={submit} className="mb-6 space-y-3 rounded-lg border border-line bg-surface p-4" aria-label="Register asset">
      <h2 className="font-semibold">Register an asset</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field id="label" label="Name / identifier">
          <input id="label" name="label" required maxLength={200} className={input} placeholder="e.g. Neem #482" aria-invalid={!!fe.label} />
          {fe.label && <p className="mt-1 text-sm text-critical">{fe.label}</p>}
        </Field>
        <Field id="kind" label="Type">
          <select id="kind" value={kind} onChange={(e) => setKind(e.target.value as AssetKind)} className={input}>
            {KINDS.map((k) => (
              <option key={k} value={k}>{label(k)}</option>
            ))}
          </select>
        </Field>
        <Field id="species_id" label="Species / crop">
          <select id="species_id" name="species_id" className={input} defaultValue="">
            <option value="">Unknown / not set</option>
            {species.data?.items.map((s) => (
              <option key={s.id} value={s.id}>{s.common_name}</option>
            ))}
          </select>
        </Field>
        <Field id="location_id" label={vocab.location}>
          <select id="location_id" name="location_id" className={input} defaultValue="">
            <option value="">None yet</option>
            {locations.data?.items.map((l) => (
              <option key={l.id} value={l.id}>{l.name}</option>
            ))}
          </select>
        </Field>
        <Field id="tag_code" label="Tag code (optional)">
          <input id="tag_code" name="tag_code" maxLength={100} className={input} />
          {fe.tag_code && <p className="mt-1 text-sm text-critical">{fe.tag_code}</p>}
        </Field>
        <Field id="planted_at" label="Planted on (optional)">
          <input id="planted_at" name="planted_at" type="date" className={input} />
        </Field>
        {kind === 'crop_batch' && (
          <Field id="estimated_count" label="Estimated plants" hint="A batch is tracked as a population.">
            <input id="estimated_count" name="estimated_count" type="number" min={1} required className={input} />
          </Field>
        )}
        <Field id="latitude" label="Latitude (optional)">
          <input id="latitude" name="latitude" inputMode="decimal" className={input} placeholder="e.g. 19.2012" />
        </Field>
        <Field id="longitude" label="Longitude (optional)">
          <input id="longitude" name="longitude" inputMode="decimal" className={input} placeholder="e.g. 72.9701" />
        </Field>
      </div>
      <Field id="notes" label="Notes (optional)">
        <textarea id="notes" name="notes" rows={2} maxLength={5000} className={input} />
      </Field>
      {create.error != null && Object.keys(fe).length === 0 && <p role="alert" className="text-sm text-critical">{errorMessage(create.error)}</p>}
      <div className="flex gap-2">
        <button className={btnPrimary} disabled={create.isPending}>{create.isPending ? 'Registering…' : 'Register asset'}</button>
        <button type="button" className={btn} onClick={onDone}>Cancel</button>
      </div>
    </form>
  )
}

function AddLocation() {
  const { ws, workspace } = useWorkspaceCtx()
  const vocab = VOCABULARY[workspace.mode]
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
      <Field id="loc" label={`New ${vocab.location.toLowerCase()}`}>
        <input id="loc" name="loc" required maxLength={200} className={input} placeholder={workspace.mode === 'agricultural_production' ? 'e.g. Field 3' : 'e.g. Ward 42 Zone 4'} />
      </Field>
      <button className={btn} disabled={create.isPending}>Add {vocab.location.toLowerCase()}</button>
      {create.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(create.error)}</p>}
    </form>
  )
}

export function AssetsPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const vocab = VOCABULARY[workspace.mode]
  const [adding, setAdding] = useState(false)
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('')
  const [band, setBand] = useState('')
  const [offset, setOffset] = useState(0)
  const list = useAssets(ws, { q, kind: kind || undefined, health_band: (band as HealthBand) || undefined, limit: PAGE, offset })
  const canRegister = atLeast(workspace.role, 'worker')

  return (
    <div>
      <PageHeader title="Assets" subtitle={`Every ${vocab.primaryAsset.toLowerCase()}, plant and crop batch in ${workspace.name}.`}>
        {canRegister && !adding && <button type="button" className={btnPrimary} onClick={() => setAdding(true)}>Register asset</button>}
      </PageHeader>
      {adding && <RegisterAssetForm onDone={() => setAdding(false)} />}
      {atLeast(workspace.role, 'manager') && <AddLocation />}

      <div className="mb-3 flex flex-wrap gap-2" role="search">
        <label className="sr-only" htmlFor="q">Search assets</label>
        <input id="q" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0) }} placeholder="Search name or tag" className={`${input} max-w-xs`} />
        <label className="sr-only" htmlFor="kindf">Filter by type</label>
        <select id="kindf" value={kind} onChange={(e) => { setKind(e.target.value); setOffset(0) }} className={`${input} max-w-[10rem]`}>
          <option value="">All types</option>
          {KINDS.map((k) => <option key={k} value={k}>{label(k)}</option>)}
        </select>
        <label className="sr-only" htmlFor="bandf">Filter by health</label>
        <select id="bandf" value={band} onChange={(e) => { setBand(e.target.value); setOffset(0) }} className={`${input} max-w-[10rem]`}>
          <option value="">Any health</option>
          <option value="healthy">Healthy</option>
          <option value="at_risk">At risk</option>
          <option value="critical">Critical</option>
        </select>
      </div>

      {list.isLoading && <LoadingBlock label="Loading assets" />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data && list.data.total === 0 && (
        <EmptyState title={q || kind || band ? 'No assets match these filters' : 'No assets yet'} action={canRegister && !adding ? <button type="button" className={btnPrimary} onClick={() => setAdding(true)}>Register the first asset</button> : undefined}>
          Registered assets appear here with their current health, open issues and tasks.
        </EmptyState>
      )}
      {list.data && list.data.total > 0 && (
        <>
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Assets</caption>
              <thead className="border-b border-line text-ink-2">
                <tr>
                  <th className="p-2 font-medium">Asset</th><th className="p-2 font-medium">Species</th>
                  <th className="p-2 font-medium">{vocab.location}</th><th className="p-2 font-medium">Health</th>
                  <th className="p-2 font-medium">Last observed</th><th className="p-2 font-medium">Issues</th><th className="p-2 font-medium">Tasks</th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((a) => (
                  <tr key={a.id} className="border-b border-line last:border-0">
                    <td className="p-2"><Link className="font-medium text-moss hover:underline" to={`/w/${ws}/assets/${a.id}`}>{a.label}</Link>{a.tag_code && <span className="ml-2 text-xs text-ink-3">{a.tag_code}</span>}</td>
                    <td className="p-2 text-ink-2">{a.species_name ?? '—'}</td>
                    <td className="p-2 text-ink-2">{a.location_name ?? '—'}</td>
                    <td className="p-2"><HealthChip band={a.state.health_band} score={a.state.health_score} /></td>
                    <td className="p-2 text-ink-2">{relative(a.state.last_observed_at)}</td>
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
