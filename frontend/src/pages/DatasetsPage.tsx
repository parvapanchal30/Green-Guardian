import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import type { DatasetItem } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { DatasetStatusChip, LicenceVerdictChip, OriginChip, isApproved } from '../components/datasets/shared'
import { Field, PageHeader, btn, btnPrimary, input } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { StatusChip } from '../components/StatusChip'
import { useCreateDataset, useDatasets, useLicencePolicy } from '../lib/datasets'
import { atLeast } from '../lib/format'

function Policy({ ws }: { ws: string }) {
  const q = useLicencePolicy(ws)
  if (q.isLoading) return <LoadingBlock label="Loading the licence policy" />
  if (q.error || !q.data) return null
  const p = q.data
  return (
    <details className="rounded-lg border border-line bg-surface p-3 text-sm">
      <summary className="cursor-pointer font-medium">Licence policy and what an approval requires</summary>
      <p className="mt-2 text-ink-2">{p.status}. Eligible: {p.eligible.join(', ')}. Excluded: {p.excluded.join('; ')}. {p.not_covered}.</p>
      <p className="mt-1 text-ink-2">Override: {p.override}.</p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-ink-2">{p.approval_requires.map((r) => <li key={r}>{r}</li>)}</ul>
      <p className="mt-2 text-ink-2">{p.download_rule}.</p>
    </details>
  )
}

function CreateForm({ ws, onDone }: { ws: string; onDone: () => void }) {
  const create = useCreateDataset(ws)
  const blank = {
    name: '', version: '', kind: 'real', source_url: '', accessed_at: '', licence_spdx: '', image_origin: 'unknown',
    has_annotations: false, commercial_use: 'unknown', redistribution: 'unknown', attribution_required: 'unknown', attribution_text: '', intended_use: '',
  }
  const [f, setF] = useState(blank)
  const set = (k: keyof typeof blank, v: string | boolean) => setF((s) => ({ ...s, [k]: v }))
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const synthetic = f.kind === 'synthetic'
    create.mutate(
      {
        name: f.name.trim(), version: f.version.trim(), kind: f.kind, source_url: synthetic ? 'synthetic://generated' : f.source_url.trim(),
        accessed_at: f.accessed_at ? new Date(f.accessed_at).toISOString() : undefined,
        licence_spdx: synthetic ? 'SYNTHETIC' : f.licence_spdx.trim(), image_origin: f.image_origin, has_annotations: f.has_annotations,
        commercial_use: f.commercial_use, redistribution: f.redistribution,
        attribution_required: f.attribution_required === 'unknown' ? undefined : f.attribution_required === 'yes',
        attribution_text: f.attribution_text.trim() || undefined, intended_use: f.intended_use.trim(),
      },
      { onSuccess: () => { setF(blank); onDone() } },
    )
  }
  const sel = (id: string, text: string, k: keyof typeof blank, options: [string, string][]) => (
    <Field id={id} label={text}><select id={id} className={input} value={String(f[k])} onChange={(e) => set(k, e.target.value)}>{options.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></Field>
  )
  const tri: [string, string][] = [['unknown', 'Not established'], ['yes', 'Yes'], ['no', 'No']]
  return (
    <form onSubmit={submit} aria-label="Propose a dataset" className="grid gap-3 rounded-lg border border-line bg-surface p-3 sm:grid-cols-2">
      <p className="text-xs text-ink-2 sm:col-span-2">Proposing a dataset records a candidate. It is not approved and nothing is downloaded. Only enter facts you have read at the source.</p>
      <Field id="d-name" label="Name"><input id="d-name" className={input} value={f.name} onChange={(e) => set('name', e.target.value)} required /></Field>
      <Field id="d-version" label="Version"><input id="d-version" className={input} value={f.version} onChange={(e) => set('version', e.target.value)} required /></Field>
      {sel('d-kind', 'Kind', 'kind', [['real', 'Real dataset'], ['synthetic', 'Synthetic test fixture (not biological data)']])}
      {f.kind === 'real' && (
        <>
          <Field id="d-url" label="Official source (https)"><input id="d-url" className={input} value={f.source_url} onChange={(e) => set('source_url', e.target.value)} required /></Field>
          <Field id="d-accessed" label="Date you read the source"><input id="d-accessed" type="date" className={input} value={f.accessed_at} onChange={(e) => set('accessed_at', e.target.value)} /></Field>
          <Field id="d-licence" label="Licence (SPDX, for example CC-BY-4.0)"><input id="d-licence" className={input} value={f.licence_spdx} onChange={(e) => set('licence_spdx', e.target.value)} required /></Field>
          {sel('d-origin', 'Image origin', 'image_origin', [['unknown', 'Unknown'], ['publisher_created', 'Made by the publisher'], ['third_party_licensed', 'Third-party, licences documented'], ['third_party_scraped', 'Scraped from third parties']])}
          {sel('d-commercial', 'Commercial use (confirmed from the licence)', 'commercial_use', tri)}
          {sel('d-redistribution', 'Redistribution', 'redistribution', tri)}
          {sel('d-attrib', 'Attribution required', 'attribution_required', tri)}
          <Field id="d-attrib-text" label="Attribution text"><input id="d-attrib-text" className={input} value={f.attribution_text} onChange={(e) => set('attribution_text', e.target.value)} /></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.has_annotations} onChange={(e) => set('has_annotations', e.target.checked)} /> Includes annotations (needs its own licence evidence)</label>
          <div className="sm:col-span-2"><Field id="d-use" label="Intended use"><textarea id="d-use" className={input} rows={2} value={f.intended_use} onChange={(e) => set('intended_use', e.target.value)} /></Field></div>
        </>
      )}
      <div className="sm:col-span-2">
        <button className={btnPrimary} disabled={create.isPending}>{create.isPending ? 'Saving…' : 'Propose dataset'}</button>
        {create.error != null && <p role="alert" className="mt-2 text-sm text-critical">{errorMessage(create.error)}</p>}
      </div>
    </form>
  )
}

function Version({ ws, d }: { ws: string; d: DatasetItem }) {
  return (
    <li className="rounded border border-line bg-canvas p-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Link to={`/w/${ws}/ai/datasets/${d.id}`} className="font-medium text-moss underline-offset-2 hover:underline">Version {d.version}</Link>
        <DatasetStatusChip status={d.status} />
        {d.kind === 'synthetic' ? <StatusChip tone="neutral">Synthetic fixture, not biological data</StatusChip> : <><LicenceVerdictChip verdict={d.licence_verdict} /><OriginChip origin={d.image_origin} /></>}
      </div>
      <p className="mt-1 text-xs text-ink-3">
        Licence {d.licence_spdx}{d.kind === 'real' && !isApproved(d) ? ` · ${d.blockers.length} open blocker${d.blockers.length === 1 ? '' : 's'}` : ''}
        {isApproved(d) ? ' · approved' : ''}
      </p>
    </li>
  )
}

function Group({ ws, title, hint, items }: { ws: string; title: string; hint: string; items: DatasetItem[] }) {
  const byName = new Map<string, DatasetItem[]>()
  for (const d of items) byName.set(d.name, [...(byName.get(d.name) ?? []), d])
  return (
    <section aria-label={title} className="space-y-2">
      <h2 className="font-semibold">{title} <span className="text-sm font-normal text-ink-3">({items.length})</span></h2>
      <p className="text-sm text-ink-2">{hint}</p>
      {items.length === 0 && <p className="text-sm text-ink-3">None.</p>}
      <ul className="space-y-3">
        {[...byName.entries()].map(([name, versions]) => (
          <li key={name} className="rounded-lg border border-line bg-surface p-3">
            <h3 className="font-medium">{name}</h3>
            <ul className="mt-2 space-y-2">{versions.map((v) => <Version key={v.id} ws={ws} d={v} />)}</ul>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function DatasetsPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const list = useDatasets(ws)
  const [adding, setAdding] = useState(false)
  const items = list.data?.items ?? []
  return (
    <div className="space-y-6">
      <PageHeader title="Datasets" subtitle="Catalog of data sources and the licence evidence behind them. A dataset is only a candidate until an owner or admin approves it. This application never downloads datasets.">
        {atLeast(workspace.role, 'manager') && <button type="button" className={btn} aria-expanded={adding} onClick={() => setAdding((v) => !v)}>{adding ? 'Close form' : 'Propose a dataset'}</button>}
      </PageHeader>
      <p className="rounded-lg border border-line bg-surface p-3 text-sm text-ink-2">
        No model is trained or evaluated here, and no dataset has been shown to be suitable for one. Approval is a licensing finding only.
      </p>
      <Policy ws={ws} />
      {adding && <CreateForm ws={ws} onDone={() => setAdding(false)} />}
      {list.isLoading && <LoadingBlock label="Loading datasets" />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data && items.length === 0 && (
        <EmptyState title="No datasets in the catalog">Candidates are proposed here and stay unapproved until their licence evidence is complete.</EmptyState>
      )}
      {list.data && items.length > 0 && (
        <>
          <Group ws={ws} title="Approved datasets" hint="Licence evidence complete and approved by an owner or admin." items={items.filter(isApproved)} />
          <Group ws={ws} title="Candidates (not approved)" hint="Proposed, under review or rejected. Do not download or use these." items={items.filter((d) => !isApproved(d))} />
        </>
      )}
    </div>
  )
}
