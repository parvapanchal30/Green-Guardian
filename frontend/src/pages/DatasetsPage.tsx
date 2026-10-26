import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import type { DatasetItem } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { DatasetStatusChip, LicenceVerdictChip, OriginChip, isApproved } from '../components/datasets/shared'
import { Field, PageHeader, btn, btnPrimary, input } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { StatusChip } from '../components/StatusChip'
import { useCreateDataset, useDatasets, useLicencePolicy } from '../lib/datasets'
import { useI18n, type TKey } from '../i18n'
import { Icon } from '../components/icons'
import { Card, SectionHeading } from '../components/ui'
import { atLeast } from '../lib/format'

function Policy({ ws }: { ws: string }) {
  const { t } = useI18n()
  const q = useLicencePolicy(ws)
  if (q.isLoading) return <LoadingBlock label={t('ds.loadingPolicy')} />
  if (q.error || !q.data) return null
  const p = q.data
  return (
    <details className="rounded-lg border border-line bg-surface px-4 py-3 text-sm">
      <summary className="cursor-pointer font-medium">{t('ds.policyTitle')}</summary>
      <p className="mt-2 text-ink-2">{p.status}. {t('ds.eligible', { list: p.eligible.join(', ') })} {t('ds.excluded', { list: p.excluded.join('; ') })} {p.not_covered}.</p>
      <p className="mt-1 text-ink-2">{t('ds.override', { text: p.override })}</p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-ink-2">{p.approval_requires.map((r) => <li key={r}>{r}</li>)}</ul>
      <p className="mt-2 text-ink-2">{p.download_rule}.</p>
    </details>
  )
}

function CreateForm({ ws, onDone }: { ws: string; onDone: () => void }) {
  const { t } = useI18n()
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
    <Field id={id} label={text}><select id={id} className={input} value={String(f[k])} onChange={(e) => set(k, e.target.value)}>{options.map(([v, text]) => <option key={v} value={v}>{text}</option>)}</select></Field>
  )
  const tri: [string, string][] = [['unknown', t('ds.form.notEstablished')], ['yes', t('ds.form.yes')], ['no', t('ds.form.no')]]
  return (
    <form onSubmit={submit} aria-label={t('ds.proposeForm')} className="grid gap-3 rounded-lg border border-line bg-surface p-4 sm:grid-cols-2">
      <p className="text-xs text-ink-2 sm:col-span-2">{t('ds.form.intro')}</p>
      <Field id="d-name" label={t('ds.form.name')}><input id="d-name" className={input} value={f.name} onChange={(e) => set('name', e.target.value)} required /></Field>
      <Field id="d-version" label={t('ds.form.version')}><input id="d-version" className={input} value={f.version} onChange={(e) => set('version', e.target.value)} required /></Field>
      {sel('d-kind', t('ds.form.kind'), 'kind', [['real', t('ds.form.real')], ['synthetic', t('ds.form.synthetic')]])}
      {f.kind === 'real' && (
        <>
          <Field id="d-url" label={t('ds.form.source')}><input id="d-url" className={input} value={f.source_url} onChange={(e) => set('source_url', e.target.value)} required /></Field>
          <Field id="d-accessed" label={t('ds.form.accessed')}><input id="d-accessed" type="date" className={input} value={f.accessed_at} onChange={(e) => set('accessed_at', e.target.value)} /></Field>
          <Field id="d-licence" label={t('ds.form.licence')}><input id="d-licence" className={input} value={f.licence_spdx} onChange={(e) => set('licence_spdx', e.target.value)} required /></Field>
          {sel('d-origin', t('ds.form.origin'), 'image_origin', [['unknown', t('ds.form.origin.unknown')], ['publisher_created', t('ds.form.origin.publisher_created')], ['third_party_licensed', t('ds.form.origin.third_party_licensed')], ['third_party_scraped', t('ds.form.origin.third_party_scraped')]])}
          {sel('d-commercial', t('ds.form.commercial'), 'commercial_use', tri)}
          {sel('d-redistribution', t('ds.form.redistribution'), 'redistribution', tri)}
          {sel('d-attrib', t('ds.form.attribRequired'), 'attribution_required', tri)}
          <Field id="d-attrib-text" label={t('ds.form.attribText')}><input id="d-attrib-text" className={input} value={f.attribution_text} onChange={(e) => set('attribution_text', e.target.value)} /></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.has_annotations} onChange={(e) => set('has_annotations', e.target.checked)} /> {t('ds.form.annotations')}</label>
          <div className="sm:col-span-2"><Field id="d-use" label={t('ds.form.intendedUse')}><textarea id="d-use" className={input} rows={2} value={f.intended_use} onChange={(e) => set('intended_use', e.target.value)} /></Field></div>
        </>
      )}
      <div className="sm:col-span-2">
        <button className={btnPrimary} disabled={create.isPending}>{create.isPending ? t('ds.saving') : t('ds.form.submit')}</button>
        {create.error != null && <p role="alert" className="mt-2 text-sm text-critical">{errorMessage(create.error)}</p>}
      </div>
    </form>
  )
}

function Version({ ws, d }: { ws: string; d: DatasetItem }) {
  const { t } = useI18n()
  return (
    <li className="rounded-md border border-line-soft bg-canvas p-2.5 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Link to={`/w/${ws}/ai/datasets/${d.id}`} className="font-medium text-moss underline-offset-2 hover:underline">{t('ds.versionN', { version: d.version })}</Link>
        <DatasetStatusChip status={d.status} />
        {d.kind === 'synthetic' ? <StatusChip tone="neutral">{t('ds.syntheticChip')}</StatusChip> : <><LicenceVerdictChip verdict={d.licence_verdict} /><OriginChip origin={d.image_origin} /></>}
      </div>
      <p className="mt-1 text-xs text-ink-3">
        {t('ds.licenceIs', { spdx: d.licence_spdx })}{d.kind === 'real' && !isApproved(d) ? ` · ${t('ds.openBlockers', { count: d.blockers.length })}` : ''}
        {isApproved(d) ? ` · ${t('ds.approvedLower')}` : ''}
      </p>
    </li>
  )
}

function Group({ ws, title, hint, items }: { ws: string; title: string; hint: string; items: DatasetItem[] }) {
  const { t } = useI18n()
  const byName = new Map<string, DatasetItem[]>()
  for (const d of items) byName.set(d.name, [...(byName.get(d.name) ?? []), d])
  return (
    <section aria-label={title} className="flex flex-col gap-2">
      <SectionHeading title={title}>
        <span className="font-mono text-xs text-ink-2">{items.length}</span>
      </SectionHeading>
      <p className="text-sm text-ink-2">{hint}</p>
      {items.length === 0 && <p className="text-sm text-ink-3">{t('ds.none')}</p>}
      <ul className="flex flex-col gap-3">
        {[...byName.entries()].map(([name, versions]) => (
          <li key={name} className="rounded-lg border border-line bg-surface p-3.5">
            <h3 className="font-display text-[17px] font-semibold">{name}</h3>
            <ul className="mt-2 flex flex-col gap-2">{versions.map((v) => <Version key={v.id} ws={ws} d={v} />)}</ul>
          </li>
        ))}
      </ul>
    </section>
  )
}

const STEPS = ['register', 'licence', 'approve', 'samples', 'split'] as const

/** The way a dataset goes from registered to ready, so the gates are visible before anyone starts (ADR-077). */
function Steps() {
  const { t } = useI18n()
  return (
    <Card className="px-4 py-3.5">
      <section aria-labelledby="ds-steps">
        <SectionHeading id="ds-steps" title={t('ds.steps.title')} />
        <ol className="flex flex-col">
          {STEPS.map((s, i) => (
            <li key={s} className="grid grid-cols-[34px_minmax(0,1fr)] gap-3 border-b border-line-soft py-2.5 last:border-0">
              <b aria-hidden="true" className="flex h-7 w-7 items-center justify-center rounded-full border-[1.5px] border-moss font-mono text-xs text-moss">{i + 1}</b>
              <span>
                <b>{t(`ds.steps.${s}` as TKey)}</b>
                <span className="block text-[13.5px] text-ink-2">{t(`ds.steps.${s}Body` as TKey)}</span>
              </span>
            </li>
          ))}
        </ol>
      </section>
    </Card>
  )
}

export function DatasetsPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const { t } = useI18n()
  const list = useDatasets(ws)
  const [adding, setAdding] = useState(false)
  const items = list.data?.items ?? []
  const canAdd = atLeast(workspace.role, 'manager')
  return (
    <div className="flex flex-col gap-4">
      <PageHeader eyebrow={t('eyebrow.insight')} title={t('ds.title')} subtitle={t('ds.subtitle')}>
        {canAdd && (
          <button type="button" className={adding ? btn : btnPrimary} aria-expanded={adding} onClick={() => setAdding((v) => !v)}>
            {!adding && <Icon name="add" size={16} />}
            {adding ? t('ds.closeForm') : t('ds.proposeForm')}
          </button>
        )}
      </PageHeader>
      <p className="max-w-prose text-sm text-ink-2">{t('ds.noModel')}</p>
      {adding && <CreateForm ws={ws} onDone={() => setAdding(false)} />}
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-5">
          {list.isLoading && <LoadingBlock label={t('ds.loading')} />}
          {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
          {list.data && items.length === 0 && (
            <EmptyState icon="datasets" title={t('ds.empty')}>
              {t('ds.emptyBody')}
            </EmptyState>
          )}
          {list.data && items.length > 0 && (
            <>
              <Group ws={ws} title={t('ds.approvedGroup')} hint={t('ds.approvedHint')} items={items.filter(isApproved)} />
              <Group ws={ws} title={t('ds.candidatesGroup')} hint={t('ds.candidatesHint')} items={items.filter((d) => !isApproved(d))} />
            </>
          )}
        </div>
        <aside className="flex flex-col gap-3.5">
          <Steps />
          <Policy ws={ws} />
        </aside>
      </div>
    </div>
  )
}
