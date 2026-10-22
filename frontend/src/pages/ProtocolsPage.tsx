import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { ProtocolDetailRecord, ProtocolRole, ProtocolStatus, ProtocolSummaryRecord, ProtocolThreshold } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { short } from '../components/datasets/shared'
import { Field, PageHeader, btn, btnPrimary, input } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { StatusChip, type Tone } from '../components/StatusChip'
import { useI18n } from '../i18n'
import { atLeast } from '../lib/format'
import { useCreateProtocol, useProtocol, useProtocolTemplate, useProtocols, useSignoff } from '../lib/protocols'

// The protocol's own content (intended use, criteria, blockers…) is server text and is shown as written.
const STATE_TONE: Record<string, Tone> = {
  awaiting_signoffs: 'building',
  awaiting_qualification_verification: 'at-risk',
  invalid_signoffs: 'critical',
  rejected: 'critical',
  superseded: 'neutral',
  approved: 'live',
}
const COMPARATOR: Record<ProtocolThreshold['comparator'], string> = { ge: '≥', le: '≤', gt: '>', lt: '<' }

function StateChip({ s }: { s: ProtocolStatus }) {
  const { te } = useI18n()
  return <StatusChip tone={STATE_TONE[s.state] ?? 'neutral'}>{te('protocolState', s.state)}</StatusChip>
}

function Standing() {
  const { t } = useI18n()
  return (
    <p className="rounded-lg border border-line bg-surface p-3 text-sm text-ink-2">
      {t('protocol.standing1')} <em>{t('protocol.standingBefore')}</em> {t('protocol.standing2')} <strong>{t('protocol.standingVerified')}</strong>
      {t('protocol.standing3')}
    </p>
  )
}

function CreateForm({ ws, onDone }: { ws: string; onDone: () => void }) {
  const { t } = useI18n()
  const tpl = useProtocolTemplate(ws, true)
  const create = useCreateProtocol(ws)
  const [key, setKey] = useState('p-dis-1')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (tpl.data) create.mutate({ key: key.trim(), content: tpl.data.content }, { onSuccess: onDone })
  }
  return (
    <form onSubmit={submit} aria-label={t('protocol.registerForm')} className="space-y-2 rounded-lg border border-line bg-surface p-3">
      {tpl.isLoading && <LoadingBlock label={t('protocol.loadingTemplate')} />}
      {tpl.error && <ErrorState error={tpl.error} />}
      {tpl.data && <p className="text-sm text-ink-2">{tpl.data.note} {t('protocol.templateNote')}</p>}
      <div className="max-w-xs"><Field id="p-key" label={t('protocol.keyLabel')}><input id="p-key" className={input} value={key} onChange={(e) => setKey(e.target.value)} pattern="[a-z0-9][a-z0-9-]*" minLength={3} required /></Field></div>
      <button className={btnPrimary} disabled={!tpl.data || create.isPending}>{create.isPending ? t('protocol.saving') : t('protocol.registerNew')}</button>
      {create.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(create.error)}</p>}
    </form>
  )
}

export function ProtocolsPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const { t } = useI18n()
  const list = useProtocols(ws)
  const [adding, setAdding] = useState(false)
  return (
    <div className="space-y-6">
      <PageHeader title={t('protocol.title')} subtitle={t('protocol.subtitle')}>
        {atLeast(workspace.role, 'manager') && <button type="button" className={btn} aria-expanded={adding} onClick={() => setAdding((v) => !v)}>{adding ? t('protocol.closeForm') : t('protocol.registerProposed')}</button>}
      </PageHeader>
      <Standing />
      {adding && <CreateForm ws={ws} onDone={() => setAdding(false)} />}
      {list.isLoading && <LoadingBlock label={t('protocol.loadingList')} />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data && list.data.total === 0 && <EmptyState title={t('protocol.none')}>{t('protocol.noneBody')}</EmptyState>}
      <ul className="space-y-2">
        {list.data?.items.map((p: ProtocolSummaryRecord) => (
          <li key={p.id} className="rounded-lg border border-line bg-surface p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Link to={`/w/${ws}/ai/protocols/${p.id}`} className="font-medium text-moss underline-offset-2 hover:underline">{p.title}</Link>
              <StatusChip tone="neutral">{t('protocol.keyVersion', { key: p.key, version: p.version })}</StatusChip>
              <StateChip s={p.status} />
            </div>
            {p.status.blockers[0] && <p className="mt-1 text-xs text-ink-3">{p.status.blockers[0]}</p>}
          </li>
        ))}
      </ul>
    </div>
  )
}

function List({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="space-y-1">
      <h3 className="font-medium">{title}</h3>
      <ul className="list-disc space-y-0.5 pl-5 text-sm text-ink-2">{items.map((i) => <li key={i}>{i}</li>)}</ul>
    </section>
  )
}

function Thresholds({ rows }: { rows: ProtocolThreshold[] }) {
  const { t, te } = useI18n()
  return (
    <section aria-labelledby="pt" className="space-y-1">
      <h3 id="pt" className="font-medium">{t('protocol.thresholds')}</h3>
      <p className="text-xs text-ink-3">{t('protocol.thresholdsNote')}</p>
      <ul className="space-y-2">
        {rows.map((th) => (
          <li key={th.id} className="rounded border border-line bg-surface p-2 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <strong>{th.metric}</strong>
              <span className="text-ink-3">({th.scope})</span>
              <code>{COMPARATOR[th.comparator]} {th.value === null ? t('protocol.noValue') : th.value}</code>
              <StatusChip tone={th.status === 'proposed' ? 'building' : 'at-risk'}>{th.status === 'proposed' ? t('protocol.proposed') : t('protocol.pendingDomain')}</StatusChip>
              <StatusChip tone="neutral">{t('protocol.basis', { basis: te('protocolBasis', th.basis) })}</StatusChip>
            </div>
            <p className="mt-1 text-ink-2">{th.justification}</p>
          </li>
        ))}
      </ul>
    </section>
  )
}

function SignoffForm({ ws, p }: { ws: string; p: ProtocolDetailRecord }) {
  const { t, te } = useI18n()
  const sign = useSignoff(ws, p.id)
  const [role, setRole] = useState<ProtocolRole>('independent_evaluator')
  const [decision, setDecision] = useState('approve')
  const [qual, setQual] = useState('')
  const [note, setNote] = useState('')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    sign.mutate({ role, decision, declared_qualification: qual.trim() || undefined, note: note.trim() }, { onSuccess: () => setNote('') })
  }
  return (
    <form onSubmit={submit} aria-label={t('protocol.signForm')} className="grid gap-3 rounded-lg border border-line bg-surface p-3 sm:grid-cols-2">
      <Field id="so-role" label={t('protocol.roleYouSign')}>
        <select id="so-role" className={input} value={role} onChange={(e) => setRole(e.target.value as ProtocolRole)}>
          {p.content.required_signoffs.map((r) => <option key={r} value={r}>{te('protocolRole', r)}</option>)}
        </select>
      </Field>
      <Field id="so-decision" label={t('protocol.decision')}>
        <select id="so-decision" className={input} value={decision} onChange={(e) => setDecision(e.target.value)}><option value="approve">{t('protocol.approve')}</option><option value="reject">{t('protocol.reject')}</option></select>
      </Field>
      <Field id="so-qual" label={t('protocol.qualification')}>
        <input id="so-qual" className={input} value={qual} onChange={(e) => setQual(e.target.value)} maxLength={300} />
      </Field>
      <Field id="so-note" label={t('protocol.note')}>
        <textarea id="so-note" className={input} rows={2} value={note} onChange={(e) => setNote(e.target.value)} minLength={10} required />
      </Field>
      <div className="sm:col-span-2">
        <button className={btnPrimary} disabled={sign.isPending || note.trim().length < 10}>{sign.isPending ? t('protocol.saving') : t('protocol.recordSignoff')}</button>
        <p className="mt-1 text-xs text-ink-3">{t('protocol.signerNote')}</p>
        {sign.error != null && <p role="alert" className="mt-2 text-sm text-critical">{errorMessage(sign.error)}</p>}
      </div>
    </form>
  )
}

export function ProtocolDetailPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const { t, te, fmt } = useI18n()
  const { protocolId = '' } = useParams()
  const q = useProtocol(ws, protocolId)
  const p = q.data
  return (
    <div className="space-y-6">
      <p className="text-sm"><Link to={`/w/${ws}/ai/protocols`} className="text-moss underline">{t('protocol.allProtocols')}</Link></p>
      {q.isLoading && <LoadingBlock label={t('protocol.loading')} />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {p && (
        <>
          <PageHeader title={p.title} subtitle={t('protocol.detailSubtitle', { key: p.key, version: p.version, checksum: p.content_sha256.slice(0, 12) })}>
            <StateChip s={p.status} />
          </PageHeader>
          <Standing />
          {p.status.blockers.length > 0 && (
            <div role="group" aria-label={t('protocol.whyNot')} className="rounded border border-at-risk p-3">
              <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">{p.status.blockers.map((b) => <li key={b}>{b}</li>)}</ul>
            </div>
          )}
          <section className="space-y-1">
            <h3 className="font-medium">{t('protocol.intendedUse')}</h3>
            <p className="text-sm text-ink-2">{p.content.intended_use}</p>
            <List title={t('protocol.notFor')} items={p.content.not_for} />
          </section>
          <section className="space-y-1">
            <h3 className="font-medium">{t('protocol.population')}</h3>
            <p className="text-sm text-ink-2">{p.content.target_population}</p>
            <p className="text-sm text-ink-2">{t('protocol.species', { list: p.content.species.join('; ') })}</p>
            <p className="text-sm text-ink-2">{t('protocol.classes', { list: p.content.disease_classes.join(', ') })}</p>
          </section>
          <List title={t('protocol.inclusion')} items={p.content.inclusion_criteria} />
          <List title={t('protocol.exclusion')} items={p.content.exclusion_criteria} />
          <List title={t('protocol.datasetReq')} items={p.content.dataset_requirements} />
          <List title={t('protocol.labelReq')} items={p.content.label_requirements} />
          <section className="space-y-1">
            <h3 className="font-medium">{t('protocol.grouping')}</h3>
            <p className="text-sm text-ink-2">{t('protocol.hierarchy', { hierarchy: p.content.grouping.hierarchy.join(' > '), unit: p.content.grouping.test_split_unit })}</p>
            <p className="text-sm text-ink-2">{p.content.grouping.claim_downgrade_if_no_site}</p>
          </section>
          <List title={t('protocol.methodology')} items={p.content.methodology} />
          <List title={t('protocol.baselines')} items={p.content.baselines} />
          <List title={t('protocol.metrics')} items={p.content.metrics} />
          <List title={t('protocol.confidence')} items={p.content.confidence_and_calibration} />
          <section className="space-y-1">
            <h3 className="font-medium">{t('protocol.errors')}</h3>
            <p className="text-sm text-ink-2"><strong>{t('protocol.fn')}</strong> {p.content.error_costs.false_negative}</p>
            <p className="text-sm text-ink-2"><strong>{t('protocol.fp')}</strong> {p.content.error_costs.false_positive}</p>
            <p className="text-sm text-ink-2"><strong>{t('protocol.operatingPoint')}</strong> {p.content.error_costs.operating_point}</p>
          </section>
          <Thresholds rows={p.content.thresholds} />
          <List title={t('protocol.prohibited')} items={p.content.prohibited_claims} />
          <List title={t('protocol.limitations')} items={p.content.limitations} />

          <section aria-labelledby="so" className="space-y-2">
            <h3 id="so" className="font-medium">{t('protocol.signoffs')}</h3>
            <p className="text-sm text-ink-2">{t('protocol.required', { roles: p.content.required_signoffs.map((r) => te('protocolRole', r)).join(', ') })}</p>
            {p.signoffs.length === 0 && <p className="text-sm text-ink-2">{t('protocol.nobody')}</p>}
            <ol className="space-y-1 text-sm">
              {p.signoffs.map((s) => (
                <li key={s.id} className="rounded border border-line bg-surface p-2">
                  <strong>{te('protocolRole', s.role)}</strong>: {s.decision === 'approve' ? t('protocol.approvedBy', { who: short(s.signer_id) }) : t('protocol.rejectedBy', { who: short(s.signer_id) })}
                  <span className="text-xs text-ink-3"> · {fmt.dateTime(s.at)}</span>
                  <p className="text-xs text-ink-3">{s.declared_qualification ? t('protocol.declared', { q: s.declared_qualification }) : t('protocol.noDeclared')} — {s.qualification_verified ? t('protocol.verified') : t('protocol.unverified')}</p>
                  <p className="text-ink-2">{s.note}</p>
                </li>
              ))}
            </ol>
            {p.status.state === 'superseded' ? (
              <p className="text-sm text-ink-2">{t('protocol.superseded')}</p>
            ) : atLeast(workspace.role, 'manager') ? (
              <SignoffForm ws={ws} p={p} />
            ) : (
              <p className="text-sm text-ink-3">{t('protocol.onlyManagers')}</p>
            )}
          </section>
        </>
      )}
    </div>
  )
}
