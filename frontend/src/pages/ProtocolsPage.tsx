import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { ProtocolDetailRecord, ProtocolRole, ProtocolStatus, ProtocolSummaryRecord, ProtocolThreshold } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { short } from '../components/datasets/shared'
import { Field, PageHeader, btn, btnPrimary, input } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { StatusChip, type Tone } from '../components/StatusChip'
import { atLeast, fmtDateTime, label } from '../lib/format'
import { useCreateProtocol, useProtocol, useProtocolTemplate, useProtocols, useSignoff } from '../lib/protocols'

const STATE: Record<string, { text: string; tone: Tone }> = {
  awaiting_signoffs: { text: 'Not approved: awaiting sign-offs', tone: 'building' },
  awaiting_qualification_verification: { text: 'Not approved: qualifications unverified', tone: 'at-risk' },
  invalid_signoffs: { text: 'Not approved: sign-offs not independent', tone: 'critical' },
  rejected: { text: 'Rejected', tone: 'critical' },
  superseded: { text: 'Superseded by a newer version', tone: 'neutral' },
  approved: { text: 'Approved', tone: 'live' },
}
const ROLE_TEXT: Record<ProtocolRole, string> = { plant_pathologist: 'Plant pathologist', data_owner: 'Data owner', independent_evaluator: 'Independent evaluator' }
const COMPARATOR: Record<ProtocolThreshold['comparator'], string> = { ge: '≥', le: '≤', gt: '>', lt: '<' }

function StateChip({ s }: { s: ProtocolStatus }) {
  const m = STATE[s.state] ?? { text: label(s.state), tone: 'neutral' as Tone }
  return <StatusChip tone={m.tone}>{m.text}</StatusChip>
}

function Standing() {
  return (
    <p className="rounded-lg border border-line bg-surface p-3 text-sm text-ink-2">
      A protocol is a plan for judging a future model, fixed <em>before</em> any model is trained. No model exists and no protocol here is approved. Approval needs three
      different people (a plant pathologist, the data owner and an independent evaluator) whose qualifications are <strong>verified</strong>; this application records the
      qualification a person declares but cannot verify it, so approval is not reachable yet.
    </p>
  )
}

function CreateForm({ ws, onDone }: { ws: string; onDone: () => void }) {
  const tpl = useProtocolTemplate(ws, true)
  const create = useCreateProtocol(ws)
  const [key, setKey] = useState('p-dis-1')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (tpl.data) create.mutate({ key: key.trim(), content: tpl.data.content }, { onSuccess: onDone })
  }
  return (
    <form onSubmit={submit} aria-label="Register a protocol version" className="space-y-2 rounded-lg border border-line bg-surface p-3">
      {tpl.isLoading && <LoadingBlock label="Loading the protocol template" />}
      {tpl.error && <ErrorState error={tpl.error} />}
      {tpl.data && <p className="text-sm text-ink-2">{tpl.data.note} Thresholds that need domain expertise are included without values.</p>}
      <div className="max-w-xs"><Field id="p-key" label="Protocol key (lower case, digits, hyphens)"><input id="p-key" className={input} value={key} onChange={(e) => setKey(e.target.value)} pattern="[a-z0-9][a-z0-9-]*" minLength={3} required /></Field></div>
      <button className={btnPrimary} disabled={!tpl.data || create.isPending}>{create.isPending ? 'Saving…' : 'Register as a new version'}</button>
      {create.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(create.error)}</p>}
    </form>
  )
}

export function ProtocolsPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const list = useProtocols(ws)
  const [adding, setAdding] = useState(false)
  return (
    <div className="space-y-6">
      <PageHeader title="Evaluation protocols" subtitle="How a future plant-disease model must be judged: data, labels, leakage control, metrics, thresholds and who must approve them.">
        {atLeast(workspace.role, 'manager') && <button type="button" className={btn} aria-expanded={adding} onClick={() => setAdding((v) => !v)}>{adding ? 'Close form' : 'Register the proposed protocol'}</button>}
      </PageHeader>
      <Standing />
      {adding && <CreateForm ws={ws} onDone={() => setAdding(false)} />}
      {list.isLoading && <LoadingBlock label="Loading protocols" />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data && list.data.total === 0 && <EmptyState title="No protocol is registered">The proposal (P-DIS-1) is available as a template. Registering it records a version; it does not approve it.</EmptyState>}
      <ul className="space-y-2">
        {list.data?.items.map((p: ProtocolSummaryRecord) => (
          <li key={p.id} className="rounded-lg border border-line bg-surface p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Link to={`/w/${ws}/ai/protocols/${p.id}`} className="font-medium text-moss underline-offset-2 hover:underline">{p.title}</Link>
              <StatusChip tone="neutral">{p.key} · version {p.version}</StatusChip>
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
  return (
    <section aria-labelledby="pt" className="space-y-1">
      <h3 id="pt" className="font-medium">Acceptance thresholds</h3>
      <p className="text-xs text-ink-3">A threshold that needs domain expertise has no value until a domain approver sets one. Nothing here is an agreed acceptance criterion.</p>
      <ul className="space-y-2">
        {rows.map((t) => (
          <li key={t.id} className="rounded border border-line bg-surface p-2 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <strong>{t.metric}</strong>
              <span className="text-ink-3">({t.scope})</span>
              <code>{COMPARATOR[t.comparator]} {t.value === null ? 'no value proposed' : t.value}</code>
              <StatusChip tone={t.status === 'proposed' ? 'building' : 'at-risk'}>{t.status === 'proposed' ? 'Proposed, needs sign-off' : 'Pending domain approval'}</StatusChip>
              <StatusChip tone="neutral">Basis: {label(t.basis)}</StatusChip>
            </div>
            <p className="mt-1 text-ink-2">{t.justification}</p>
          </li>
        ))}
      </ul>
    </section>
  )
}

function SignoffForm({ ws, p }: { ws: string; p: ProtocolDetailRecord }) {
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
    <form onSubmit={submit} aria-label="Record a sign-off" className="grid gap-3 rounded-lg border border-line bg-surface p-3 sm:grid-cols-2">
      <Field id="so-role" label="Role you sign in">
        <select id="so-role" className={input} value={role} onChange={(e) => setRole(e.target.value as ProtocolRole)}>
          {p.content.required_signoffs.map((r) => <option key={r} value={r}>{ROLE_TEXT[r]}</option>)}
        </select>
      </Field>
      <Field id="so-decision" label="Decision">
        <select id="so-decision" className={input} value={decision} onChange={(e) => setDecision(e.target.value)}><option value="approve">Approve</option><option value="reject">Reject</option></select>
      </Field>
      <Field id="so-qual" label="Your qualification (self-declared; the application does not verify it)">
        <input id="so-qual" className={input} value={qual} onChange={(e) => setQual(e.target.value)} maxLength={300} />
      </Field>
      <Field id="so-note" label="Note: what you checked (at least 10 characters)">
        <textarea id="so-note" className={input} rows={2} value={note} onChange={(e) => setNote(e.target.value)} minLength={10} required />
      </Field>
      <div className="sm:col-span-2">
        <button className={btnPrimary} disabled={sign.isPending || note.trim().length < 10}>{sign.isPending ? 'Saving…' : 'Record sign-off'}</button>
        <p className="mt-1 text-xs text-ink-3">The signer recorded is you. The data-owner role can only be signed by the workspace owner; the server enforces this.</p>
        {sign.error != null && <p role="alert" className="mt-2 text-sm text-critical">{errorMessage(sign.error)}</p>}
      </div>
    </form>
  )
}

export function ProtocolDetailPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const { protocolId = '' } = useParams()
  const q = useProtocol(ws, protocolId)
  const p = q.data
  return (
    <div className="space-y-6">
      <p className="text-sm"><Link to={`/w/${ws}/ai/protocols`} className="text-moss underline">← All protocols</Link></p>
      {q.isLoading && <LoadingBlock label="Loading protocol" />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {p && (
        <>
          <PageHeader title={p.title} subtitle={`${p.key} · version ${p.version} · checksum ${p.content_sha256.slice(0, 12)}`}>
            <StateChip s={p.status} />
          </PageHeader>
          <Standing />
          {p.status.blockers.length > 0 && (
            <div role="group" aria-label="Why this protocol is not approved" className="rounded border border-at-risk p-3">
              <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">{p.status.blockers.map((b) => <li key={b}>{b}</li>)}</ul>
            </div>
          )}
          <section className="space-y-1">
            <h3 className="font-medium">Intended use</h3>
            <p className="text-sm text-ink-2">{p.content.intended_use}</p>
            <List title="Not for" items={p.content.not_for} />
          </section>
          <section className="space-y-1">
            <h3 className="font-medium">Target population, species and classes</h3>
            <p className="text-sm text-ink-2">{p.content.target_population}</p>
            <p className="text-sm text-ink-2">Species: {p.content.species.join('; ')}</p>
            <p className="text-sm text-ink-2">Classes: {p.content.disease_classes.join(', ')}</p>
          </section>
          <List title="Inclusion criteria" items={p.content.inclusion_criteria} />
          <List title="Exclusion criteria" items={p.content.exclusion_criteria} />
          <List title="Dataset requirements" items={p.content.dataset_requirements} />
          <List title="Label requirements" items={p.content.label_requirements} />
          <section className="space-y-1">
            <h3 className="font-medium">Grouping (leakage control)</h3>
            <p className="text-sm text-ink-2">Hierarchy: {p.content.grouping.hierarchy.join(' > ')}. Test split unit: {p.content.grouping.test_split_unit}.</p>
            <p className="text-sm text-ink-2">{p.content.grouping.claim_downgrade_if_no_site}</p>
          </section>
          <List title="Training, validation and held-out test methodology" items={p.content.methodology} />
          <List title="Baselines" items={p.content.baselines} />
          <List title="Metrics" items={p.content.metrics} />
          <List title="Confidence intervals and calibration" items={p.content.confidence_and_calibration} />
          <section className="space-y-1">
            <h3 className="font-medium">Errors and their costs</h3>
            <p className="text-sm text-ink-2"><strong>False negative:</strong> {p.content.error_costs.false_negative}</p>
            <p className="text-sm text-ink-2"><strong>False positive:</strong> {p.content.error_costs.false_positive}</p>
            <p className="text-sm text-ink-2"><strong>Operating point:</strong> {p.content.error_costs.operating_point}</p>
          </section>
          <Thresholds rows={p.content.thresholds} />
          <List title="Claims that are prohibited" items={p.content.prohibited_claims} />
          <List title="Limitations" items={p.content.limitations} />

          <section aria-labelledby="so" className="space-y-2">
            <h3 id="so" className="font-medium">Sign-offs</h3>
            <p className="text-sm text-ink-2">Required: {p.content.required_signoffs.map((r) => ROLE_TEXT[r]).join(', ')}, each a different person.</p>
            {p.signoffs.length === 0 && <p className="text-sm text-ink-2">Nobody has signed.</p>}
            <ol className="space-y-1 text-sm">
              {p.signoffs.map((s) => (
                <li key={s.id} className="rounded border border-line bg-surface p-2">
                  <strong>{ROLE_TEXT[s.role]}</strong>: {s.decision === 'approve' ? 'approved' : 'rejected'} by {short(s.signer_id)}
                  <span className="text-xs text-ink-3"> · {fmtDateTime(s.at)}</span>
                  <p className="text-xs text-ink-3">{s.declared_qualification ? `Declared qualification: “${s.declared_qualification}”` : 'No qualification declared'} — {s.qualification_verified ? 'verified' : 'unverified'}</p>
                  <p className="text-ink-2">{s.note}</p>
                </li>
              ))}
            </ol>
            {p.status.state === 'superseded' ? (
              <p className="text-sm text-ink-2">This version has been superseded; sign the newest version.</p>
            ) : atLeast(workspace.role, 'manager') ? (
              <SignoffForm ws={ws} p={p} />
            ) : (
              <p className="text-sm text-ink-3">Only managers and owners can record a sign-off.</p>
            )}
          </section>
        </>
      )}
    </div>
  )
}
