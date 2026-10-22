import { useState } from 'react'
import type { DatasetDetailRecord, QualityIssue, Role, SplitRecord } from '../../api/types'
import { useI18n } from '../../i18n'
import { atLeast } from '../../lib/format'
import { useClaimReadiness, useCreateSplit, useDatasetAgreement, useDatasetQuality, useDatasetSplits } from '../../lib/datasets'
import { Field, btnPrimary, input } from '../domain'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../states'
import { StatusChip, type Tone } from '../StatusChip'
import { short } from './shared'

// Issue, warning, caveat and blocker messages come from the server and are shown as written.
const SEVERITY: Record<QualityIssue['severity'], Tone> = { error: 'critical', warning: 'at-risk', info: 'neutral' }

export function QualityTab({ ws, d }: { ws: string; d: DatasetDetailRecord }) {
  const { t, te } = useI18n()
  const q = useDatasetQuality(ws, d.id)
  if (q.isLoading) return <LoadingBlock label={t('ds.q.loading')} />
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const r = q.data
  if (!r || r.samples === 0) return <EmptyState title={t('ds.q.empty')}>{t('ds.q.emptyBody')}</EmptyState>
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-2">{t('ds.q.mechanical')}</p>
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip tone={r.passed ? 'live' : 'critical'}>{r.passed ? t('ds.q.passed') : t('ds.q.failed')}</StatusChip>
        <span className="text-sm">{t('ds.q.samples', { n: r.samples })}</span>
        {r.reviewed_fraction !== undefined && <span className="text-sm">{t('ds.q.reviewedPct', { pct: Math.round(r.reviewed_fraction * 100) })}</span>}
      </div>
      <ul aria-label={t('ds.q.issues')} className="space-y-2">
        {r.issues.map((i) => (
          <li key={i.code} className="rounded-lg border border-line bg-surface p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <StatusChip tone={SEVERITY[i.severity]}>{te('qualitySeverity', i.severity)}</StatusChip>
              <code>{i.code}</code>
              {i.count > 0 && <span className="text-ink-3">{t('ds.q.affected', { n: i.count })}</span>}
            </div>
            <p className="mt-1 text-ink-2">{i.message}</p>
            {i.examples.length > 0 && <p className="text-xs text-ink-3">{t('ds.q.examples', { list: i.examples.join(', ') })}</p>}
          </li>
        ))}
        {r.issues.length === 0 && <li className="text-sm text-ink-2">{t('ds.q.noIssues')}</li>}
      </ul>
      {r.classes?.counts && (
        <section aria-labelledby="q-classes">
          <h3 id="q-classes" className="font-medium">{t('ds.q.classes')}</h3>
          <ul className="mt-1 flex flex-wrap gap-2 text-sm">
            {Object.entries(r.classes.counts).map(([k, v]) => <li key={k}><StatusChip tone="neutral">{k}: {v}</StatusChip></li>)}
          </ul>
          {r.classes.max_over_min !== undefined && <p className="mt-1 text-xs text-ink-3">{t('ds.q.imbalance', { ratio: r.classes.max_over_min })}</p>}
        </section>
      )}
      {r.groups && <p className="text-sm text-ink-2">{t('ds.q.groups', { count: r.groups.count, largest: r.groups.largest })}</p>}
    </div>
  )
}

function SplitCard({ s }: { s: SplitRecord }) {
  const { t, fmt } = useI18n()
  return (
    <li className="rounded-lg border border-line bg-surface p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <strong>{t('ds.versionN', { version: s.version })}</strong>
        <span className="text-xs text-ink-3">{t('ds.sp.meta', { seed: s.seed, when: fmt.dateTime(s.created_at) })} <code>{s.manifest_sha256.slice(0, 12)}</code></span>
        {s.include_unreviewed && <StatusChip tone="at-risk">{t('ds.sp.unreviewed')}</StatusChip>}
        <StatusChip tone={s.leakage_violations.length ? 'critical' : 'live'}>
          {s.leakage_violations.length ? t('ds.sp.leakage', { n: s.leakage_violations.length }) : t('ds.sp.noLeakage')}
        </StatusChip>
      </div>
      <table className="mt-2 w-full text-left text-xs">
        <thead><tr className="text-ink-3"><th className="p-1">{t('ds.sp.split')}</th><th className="p-1">{t('ds.sp.items')}</th><th className="p-1">{t('ds.sp.groups')}</th><th className="p-1">{t('ds.sp.share')}</th></tr></thead>
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
  const { t } = useI18n()
  const q = useDatasetSplits(ws, d.id)
  const create = useCreateSplit(ws, d.id)
  const [seed, setSeed] = useState('0')
  const [unreviewed, setUnreviewed] = useState(false)
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-2">{t('ds.sp.intro')}</p>
      {atLeast(role, 'manager') && (
        <form
          aria-label={t('ds.sp.form')}
          className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-surface p-3"
          onSubmit={(e) => { e.preventDefault(); create.mutate({ seed: Number(seed) || 0, include_unreviewed: unreviewed }) }}
        >
          <div className="w-28"><Field id="split-seed" label={t('ds.sp.seed')}><input id="split-seed" type="number" min={0} className={input} value={seed} onChange={(e) => setSeed(e.target.value)} /></Field></div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={unreviewed} onChange={(e) => setUnreviewed(e.target.checked)} /> {t('ds.sp.includeUnreviewed')}</label>
          <button className={btnPrimary} disabled={create.isPending}>{create.isPending ? t('ds.sp.creating') : t('ds.sp.create')}</button>
          {create.error != null && <p role="alert" className="w-full text-sm text-critical">{errorMessage(create.error)}</p>}
        </form>
      )}
      {q.isLoading && <LoadingBlock label={t('ds.sp.loading')} />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && q.data.length === 0 && <EmptyState title={t('ds.sp.none')}>{t('ds.sp.noneBody')}</EmptyState>}
      <ul className="space-y-2">{q.data?.map((s) => <SplitCard key={s.id} s={s} />)}</ul>
    </div>
  )
}

export function AgreementTab({ ws, d }: { ws: string; d: DatasetDetailRecord }) {
  const { t } = useI18n()
  const q = useDatasetAgreement(ws, d.id)
  if (q.isLoading) return <LoadingBlock label={t('ds.ag.loading')} />
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const r = q.data
  if (!r) return null
  return (
    <div className="space-y-4">
      <p className="rounded-lg border border-line bg-surface p-3 text-sm text-ink-2">{t('ds.unverifiedNote')}</p>
      <dl className="grid gap-3 sm:grid-cols-4">
        <div><dt className="text-xs text-ink-3">{t('ds.ag.decided')}</dt><dd>{r.samples_with_a_decision}</dd></div>
        <div><dt className="text-xs text-ink-3">{t('ds.ag.twoReviewers')}</dt><dd>{r.samples_with_two_reviewers}</dd></div>
        <div><dt className="text-xs text-ink-3">{t('ds.ag.observed')}</dt><dd>{r.observed_agreement === null ? t('ds.ag.notAvailable') : `${Math.round(r.observed_agreement * 100)}%`}</dd></div>
        <div><dt className="text-xs text-ink-3">{t('ds.ag.kappa')}</dt><dd>{r.cohens_kappa === null ? t('ds.ag.notComputed') : r.cohens_kappa.toFixed(2)}</dd></div>
      </dl>
      <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">{r.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
      {r.disagreements.length > 0 && (
        <section aria-labelledby="agr-dis">
          <h3 id="agr-dis" className="font-medium">{t('ds.ag.disagreements')}</h3>
          <ul className="mt-1 space-y-1 text-sm">{r.disagreements.map((x) => <li key={x.sample_id}>{t('ds.ag.sample', { id: x.external_id ?? short(x.sample_id) })}: {x.verdicts.join(' vs ')}</li>)}</ul>
        </section>
      )}
    </div>
  )
}

export function ClaimsTab({ ws, d }: { ws: string; d: DatasetDetailRecord }) {
  const { t } = useI18n()
  const q = useClaimReadiness(ws, d.id)
  if (q.isLoading) return <LoadingBlock label={t('ds.cl.loading')} />
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const r = q.data
  if (!r) return null
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip tone={r.allowed ? 'at-risk' : 'critical'}>{r.allowed ? t('ds.cl.allowed') : t('ds.cl.blocked')}</StatusChip>
        {r.split_version !== null && <span className="text-sm text-ink-3">{t('ds.cl.basedOn', { version: r.split_version })}</span>}
      </div>
      <ul aria-label={t('ds.cl.blockers')} className="space-y-2">
        {r.blockers.map((b) => (
          <li key={b.code} className="rounded-lg border border-line bg-surface p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <code>{b.code}</code>
              {!b.resolvable_in_application && <StatusChip tone="at-risk">{t('ds.cl.outside')}</StatusChip>}
            </div>
            <p className="mt-1 text-ink-2">{b.message}</p>
          </li>
        ))}
      </ul>
      <p className="text-xs text-ink-3">{r.note}</p>
    </div>
  )
}
