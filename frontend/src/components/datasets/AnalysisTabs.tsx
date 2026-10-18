import { useState } from 'react'
import type { DatasetDetailRecord, QualityIssue, Role, SplitRecord } from '../../api/types'
import { atLeast, fmtDateTime, label } from '../../lib/format'
import { useClaimReadiness, useCreateSplit, useDatasetAgreement, useDatasetQuality, useDatasetSplits } from '../../lib/datasets'
import { Field, btnPrimary, input } from '../domain'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../states'
import { StatusChip, type Tone } from '../StatusChip'
import { UNVERIFIED_NOTE, short } from './shared'

const SEVERITY: Record<QualityIssue['severity'], Tone> = { error: 'critical', warning: 'at-risk', info: 'neutral' }

export function QualityTab({ ws, d }: { ws: string; d: DatasetDetailRecord }) {
  const q = useDatasetQuality(ws, d.id)
  if (q.isLoading) return <LoadingBlock label="Loading quality report" />
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const r = q.data
  if (!r || r.samples === 0) return <EmptyState title="No samples to check">The quality report runs over registered samples. None are registered, so there is nothing to report.</EmptyState>
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-2">These are mechanical checks. Passing them does not make labels correct or the data representative.</p>
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip tone={r.passed ? 'live' : 'critical'}>{r.passed ? 'No error-level issues' : 'Has error-level issues'}</StatusChip>
        <span className="text-sm">{r.samples} samples</span>
        {r.reviewed_fraction !== undefined && <span className="text-sm">{Math.round(r.reviewed_fraction * 100)}% of labels reviewed</span>}
      </div>
      <ul aria-label="Quality issues" className="space-y-2">
        {r.issues.map((i) => (
          <li key={i.code} className="rounded-lg border border-line bg-surface p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <StatusChip tone={SEVERITY[i.severity]}>{label(i.severity)}</StatusChip>
              <code>{i.code}</code>
              {i.count > 0 && <span className="text-ink-3">{i.count} affected</span>}
            </div>
            <p className="mt-1 text-ink-2">{i.message}</p>
            {i.examples.length > 0 && <p className="text-xs text-ink-3">e.g. {i.examples.join(', ')}</p>}
          </li>
        ))}
        {r.issues.length === 0 && <li className="text-sm text-ink-2">No issues were found by these checks.</li>}
      </ul>
      {r.classes?.counts && (
        <section aria-labelledby="q-classes">
          <h3 id="q-classes" className="font-medium">Classes</h3>
          <ul className="mt-1 flex flex-wrap gap-2 text-sm">
            {Object.entries(r.classes.counts).map(([k, v]) => <li key={k}><StatusChip tone="neutral">{k}: {v}</StatusChip></li>)}
          </ul>
          {r.classes.max_over_min !== undefined && <p className="mt-1 text-xs text-ink-3">Largest class over smallest: {r.classes.max_over_min}×</p>}
        </section>
      )}
      {r.groups && <p className="text-sm text-ink-2">{r.groups.count} groups; the largest has {r.groups.largest} samples.</p>}
    </div>
  )
}

function SplitCard({ s }: { s: SplitRecord }) {
  return (
    <li className="rounded-lg border border-line bg-surface p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <strong>Version {s.version}</strong>
        <span className="text-xs text-ink-3">seed {s.seed} · {fmtDateTime(s.created_at)} · checksum <code>{s.manifest_sha256.slice(0, 12)}</code></span>
        {s.include_unreviewed && <StatusChip tone="at-risk">Includes unreviewed labels</StatusChip>}
        <StatusChip tone={s.leakage_violations.length ? 'critical' : 'live'}>
          {s.leakage_violations.length ? `${s.leakage_violations.length} leakage violation(s)` : 'No leakage found by the checker'}
        </StatusChip>
      </div>
      <table className="mt-2 w-full text-left text-xs">
        <thead><tr className="text-ink-3"><th className="p-1">Split</th><th className="p-1">Items</th><th className="p-1">Groups</th><th className="p-1">Share (target)</th></tr></thead>
        <tbody>
          {Object.entries(s.stats).map(([name, v]) => (
            <tr key={name} className="border-t border-line">
              <td className="p-1">{name}</td><td className="p-1">{v.items}</td><td className="p-1">{v.groups}</td>
              <td className="p-1">{Math.round(v.actual_fraction * 100)}% ({Math.round(v.target_fraction * 100)}%)</td>
            </tr>
          ))}
        </tbody>
      </table>
      {s.warnings.length > 0 && <ul className="mt-2 list-disc pl-5 text-ink-2">{s.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
    </li>
  )
}

export function SplitsTab({ ws, d, role }: { ws: string; d: DatasetDetailRecord; role: Role }) {
  const q = useDatasetSplits(ws, d.id)
  const create = useCreateSplit(ws, d.id)
  const [seed, setSeed] = useState('0')
  const [unreviewed, setUnreviewed] = useState(false)
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-2">Whole groups (for example one plant or field) go to exactly one split, so near-copies cannot sit on both sides of an evaluation. Splits are versioned and cannot be edited.</p>
      {atLeast(role, 'manager') && (
        <form
          aria-label="Create a split"
          className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-surface p-3"
          onSubmit={(e) => { e.preventDefault(); create.mutate({ seed: Number(seed) || 0, include_unreviewed: unreviewed }) }}
        >
          <div className="w-28"><Field id="split-seed" label="Seed"><input id="split-seed" type="number" min={0} className={input} value={seed} onChange={(e) => setSeed(e.target.value)} /></Field></div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={unreviewed} onChange={(e) => setUnreviewed(e.target.checked)} /> Include labels that are not reviewed (engineering checks only, never for claims)</label>
          <button className={btnPrimary} disabled={create.isPending}>{create.isPending ? 'Creating…' : 'Create split (70 / 15 / 15)'}</button>
          {create.error != null && <p role="alert" className="w-full text-sm text-critical">{errorMessage(create.error)}</p>}
        </form>
      )}
      {q.isLoading && <LoadingBlock label="Loading splits" />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && q.data.length === 0 && <EmptyState title="No split yet">A split needs reviewed, labelled, grouped samples from an approved dataset.</EmptyState>}
      <ul className="space-y-2">{q.data?.map((s) => <SplitCard key={s.id} s={s} />)}</ul>
    </div>
  )
}

export function AgreementTab({ ws, d }: { ws: string; d: DatasetDetailRecord }) {
  const q = useDatasetAgreement(ws, d.id)
  if (q.isLoading) return <LoadingBlock label="Loading reviewer agreement" />
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const r = q.data
  if (!r) return null
  return (
    <div className="space-y-4">
      <p className="rounded-lg border border-line bg-surface p-3 text-sm text-ink-2">{UNVERIFIED_NOTE}</p>
      <dl className="grid gap-3 sm:grid-cols-4">
        <div><dt className="text-xs text-ink-3">Samples decided</dt><dd>{r.samples_with_a_decision}</dd></div>
        <div><dt className="text-xs text-ink-3">Decided by two reviewers</dt><dd>{r.samples_with_two_reviewers}</dd></div>
        <div><dt className="text-xs text-ink-3">Observed agreement</dt><dd>{r.observed_agreement === null ? 'not available' : `${Math.round(r.observed_agreement * 100)}%`}</dd></div>
        <div><dt className="text-xs text-ink-3">Cohen’s kappa</dt><dd>{r.cohens_kappa === null ? 'not computed' : r.cohens_kappa.toFixed(2)}</dd></div>
      </dl>
      <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">{r.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
      {r.disagreements.length > 0 && (
        <section aria-labelledby="agr-dis">
          <h3 id="agr-dis" className="font-medium">Disagreements</h3>
          <ul className="mt-1 space-y-1 text-sm">{r.disagreements.map((x) => <li key={x.sample_id}>sample {x.external_id ?? short(x.sample_id)}: {x.verdicts.join(' vs ')}</li>)}</ul>
        </section>
      )}
    </div>
  )
}

export function ClaimsTab({ ws, d }: { ws: string; d: DatasetDetailRecord }) {
  const q = useClaimReadiness(ws, d.id)
  if (q.isLoading) return <LoadingBlock label="Loading claim readiness" />
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const r = q.data
  if (!r) return null
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip tone={r.allowed ? 'at-risk' : 'critical'}>{r.allowed ? 'No blocker found (this is not proof of quality)' : 'Performance claims are blocked'}</StatusChip>
        {r.split_version !== null && <span className="text-sm text-ink-3">based on split version {r.split_version}</span>}
      </div>
      <ul aria-label="Claim blockers" className="space-y-2">
        {r.blockers.map((b) => (
          <li key={b.code} className="rounded-lg border border-line bg-surface p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <code>{b.code}</code>
              {!b.resolvable_in_application && <StatusChip tone="at-risk">Cannot be cleared inside this application</StatusChip>}
            </div>
            <p className="mt-1 text-ink-2">{b.message}</p>
          </li>
        ))}
      </ul>
      <p className="text-xs text-ink-3">{r.note}</p>
    </div>
  )
}
