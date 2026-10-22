import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ProblemError } from '../api/client'
import type { AuditEvent } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { Field, PageHeader, Pagination, btn, btnPrimary, input } from '../components/domain'
import { StatusChip, type Tone } from '../components/StatusChip'
import { EmptyState, ErrorState, LoadingBlock } from '../components/states'
import { useI18n } from '../i18n'
import { atLeast, toIsoOrUndefined } from '../lib/format'
import { useAudit, useAuditMeta } from '../lib/slice'

const PAGE = 25
const OUTCOME_TONE: Record<AuditEvent['outcome'], Tone> = { success: 'live', failure: 'critical', denied: 'at-risk' }
/** Targets that have a page of their own. Others (users, workspaces, recommendations…) are shown as text. */
const TARGET_PATH: Record<string, string> = { asset: 'assets', issue: 'issues' }

interface Filters { action: string; target_type: string; request_id: string; since: string; until: string }
const EMPTY: Filters = { action: '', target_type: '', request_id: '', since: '', until: '' }

function Target({ ws, e }: { ws: string; e: AuditEvent }) {
  if (!e.target_type) return <span className="text-ink-3">—</span>
  const short = e.target_id ? e.target_id.slice(0, 8) : ''
  const path = TARGET_PATH[e.target_type]
  return (
    <span>
      {e.target_type}
      {e.target_id && (path ? <> · <Link className="text-moss underline" to={`/w/${ws}/${path}/${e.target_id}`}>{short}</Link></> : <> · <span className="font-mono text-xs">{short}</span></>)}
    </span>
  )
}

function Row({ ws, e, onFilterRequest }: { ws: string; e: AuditEvent; onFilterRequest: (id: string) => void }) {
  const { t, te, fmt } = useI18n()
  return (
    <tr className="border-b border-line align-top last:border-0">
      <td className="whitespace-nowrap p-2"><time dateTime={e.occurred_at} title={e.occurred_at}>{fmt.dateTime(e.occurred_at)}</time></td>
      <td className="p-2">{e.actor_name ?? <span className="text-ink-3">{t('audit.system')}</span>}</td>
      <td className="p-2 font-mono text-xs">{e.action}</td>
      <td className="p-2"><StatusChip tone={OUTCOME_TONE[e.outcome]}>{te('auditOutcome', e.outcome)}</StatusChip></td>
      <td className="p-2"><Target ws={ws} e={e} /></td>
      <td className="p-2">
        {e.request_id ? (
          <button type="button" className="font-mono text-xs text-moss underline" title={t('audit.showRequest')} onClick={() => onFilterRequest(e.request_id!)}>
            {e.request_id.slice(0, 10)}…
          </button>
        ) : <span className="text-ink-3">—</span>}
      </td>
      <td className="p-2">
        <details>
          <summary className="cursor-pointer text-xs text-ink-2">{t('audit.details')}</summary>
          {/* Rendered as text: React escapes it, so stored values can never execute. */}
          <pre className="mt-1 max-w-xs overflow-x-auto whitespace-pre-wrap rounded bg-surface-2 p-2 text-xs">{JSON.stringify({ ...e.details, client_ip: e.client_ip, request_id: e.request_id }, null, 2)}</pre>
        </details>
      </td>
    </tr>
  )
}

export function AuditPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const { t } = useI18n()
  const allowed = atLeast(workspace.role, 'manager')
  const [draft, setDraft] = useState<Filters>(EMPTY)
  const [applied, setApplied] = useState<Filters>(EMPTY)
  const [offset, setOffset] = useState(0)
  const meta = useAuditMeta(ws, allowed)
  const list = useAudit(
    ws,
    {
    action: applied.action || undefined,
    target_type: applied.target_type || undefined,
    request_id: applied.request_id.trim() || undefined,
    since: toIsoOrUndefined(applied.since),
    until: toIsoOrUndefined(applied.until),
    limit: PAGE,
    offset,
  },
    allowed,
  )

  if (!allowed) {
    return (
      <div className="space-y-4">
        <PageHeader title={t('audit.title')} />
        <ErrorState error={new ProblemError(403, 'insufficient_role', t('audit.forbidden'))} />
      </div>
    )
  }

  const apply = (next: Filters) => { setApplied(next); setDraft(next); setOffset(0) }
  const submit = (e: FormEvent) => { e.preventDefault(); apply(draft) }
  const filtered = JSON.stringify(applied) !== JSON.stringify(EMPTY)
  const retention = meta.data
    ? meta.data.retention_days === 0 ? t('audit.keptForever') : t('audit.keptDays', { days: meta.data.retention_days })
    : null

  return (
    <div className="space-y-4">
      <PageHeader title={t('audit.title')} subtitle={t('audit.subtitle')} />
      {retention && <p className="text-sm text-ink-2">{retention}</p>}

      <form onSubmit={submit} aria-label={t('audit.filter')} className="grid gap-3 rounded-lg border border-line bg-surface p-3 sm:grid-cols-2 lg:grid-cols-5">
        <Field id="f-action" label={t('audit.action')}>
          <select id="f-action" className={input} value={draft.action} onChange={(e) => setDraft({ ...draft, action: e.target.value })}>
            <option value="">{t('audit.allActions')}</option>
            {meta.data?.actions.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </Field>
        <Field id="f-target" label={t('audit.targetType')}>
          <select id="f-target" className={input} value={draft.target_type} onChange={(e) => setDraft({ ...draft, target_type: e.target.value })}>
            <option value="">{t('audit.all')}</option>
            {meta.data?.target_types.map((tt) => <option key={tt} value={tt}>{tt}</option>)}
          </select>
        </Field>
        <Field id="f-request" label={t('audit.requestId')}>
          <input id="f-request" className={`${input} font-mono`} value={draft.request_id} onChange={(e) => setDraft({ ...draft, request_id: e.target.value })} maxLength={64} />
        </Field>
        <Field id="f-since" label={t('audit.from')}>
          <input id="f-since" type="datetime-local" className={input} value={draft.since} onChange={(e) => setDraft({ ...draft, since: e.target.value })} />
        </Field>
        <Field id="f-until" label={t('audit.until')}>
          <input id="f-until" type="datetime-local" className={input} value={draft.until} onChange={(e) => setDraft({ ...draft, until: e.target.value })} />
        </Field>
        <div className="flex gap-2 sm:col-span-2 lg:col-span-5">
          <button className={btnPrimary}>{t('audit.apply')}</button>
          <button type="button" className={btn} disabled={!filtered && JSON.stringify(draft) === JSON.stringify(EMPTY)} onClick={() => apply(EMPTY)}>{t('audit.reset')}</button>
        </div>
      </form>

      {list.isLoading && <LoadingBlock label={t('audit.loading')} />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data && list.data.items.length === 0 && (
        <EmptyState title={filtered ? t('audit.noMatch') : t('audit.none')}>
          {filtered ? t('audit.noMatchBody') : t('audit.noneBody')}
        </EmptyState>
      )}
      {list.data && list.data.items.length > 0 && (
        <>
          <p className="text-sm text-ink-2">{t('audit.count', { count: list.data.total })}</p>
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">{t('audit.caption')}</caption>
              <thead className="border-b border-line text-ink-2">
                <tr>{(['when', 'actor', 'action', 'outcome', 'target', 'request'] as const).map((h) => <th key={h} className="p-2 font-medium">{t(`audit.col.${h}`)}</th>)}<th className="p-2" /></tr>
              </thead>
              <tbody>{list.data.items.map((e) => <Row key={e.id} ws={ws} e={e} onFilterRequest={(id) => apply({ ...EMPTY, request_id: id })} />)}</tbody>
            </table>
          </div>
          <Pagination total={list.data.total} limit={PAGE} offset={offset} onChange={setOffset} />
        </>
      )}
    </div>
  )
}
