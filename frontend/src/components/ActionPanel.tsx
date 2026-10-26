import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import type { ActionRecord, Asset, Role } from '../api/types'
import { useI18n } from '../i18n'
import { ACTION_KINDS, ACTION_UNITS, MIN_REASON, amount, useActions, useCorrectAction, useRecordAction } from '../lib/actions'
import { atLeast } from '../lib/format'
import { enteredAt } from '../lib/lifecycle'
import { useMembers } from '../lib/queries'
import { useIssues } from '../lib/slice'
import { Field, btn, btnPrimary, input } from './domain'
import { ErrorState, LoadingBlock, errorMessage } from './states'
import { StatusChip } from './StatusChip'

/** One line per record: what, how much, with what, when, by whom, and its links. Replaced records are struck through. */
export function ActionList({ ws, actions, onCorrect }: { ws: string; actions: ActionRecord[]; onCorrect?: (a: ActionRecord) => void }) {
  const { t, te, fmt } = useI18n()
  const members = useMembers(ws)
  const who = (id: string | null) => members.data?.find((m) => m.user_id === id)?.name ?? null
  return (
    <ol aria-label={t('action.history')} className="space-y-1 text-sm">
      {actions.map((a) => (
        <li key={a.id} className={`flex flex-wrap items-baseline gap-x-2 ${a.effective ? '' : 'text-ink-3 line-through decoration-1'}`}>
          <span className="text-xs text-ink-3">{fmt.dateTime(a.performed_at)}</span>
          <span className="font-medium">{te('actionKind', a.kind)}</span>
          {a.quantity != null && a.unit && <span>{fmt.number(a.quantity, { maximumFractionDigits: 3 })} {te('unit', a.unit)}</span>}
          {a.product && <span>{a.product}</span>}
          {who(a.performed_by) && <span className="text-ink-2">{t('action.by', { name: who(a.performed_by) ?? '' })}</span>}
          {a.issue_id && <Link className="text-moss hover:underline" to={`/w/${ws}/issues/${a.issue_id}`}>{a.issue_key}</Link>}
          {a.task_key && <span className="text-xs text-ink-3">{t('action.forTask', { key: a.task_key })}</span>}
          {a.follow_up_task_key && <StatusChip tone="building">{t('action.followUpTask', { key: a.follow_up_task_key })}</StatusChip>}
          {a.supersedes_id && <StatusChip tone="at-risk">{a.withdrawn ? t('action.withdrawn') : t('action.correctionChip')}</StatusChip>}
          {!a.effective && <StatusChip tone="neutral">{t('action.replaced')}</StatusChip>}
          {a.note && <span className="text-ink-2">{a.note}</span>}
          {onCorrect && a.effective && !a.withdrawn && (
            <button type="button" className={`${btn} px-2 py-0.5 text-xs`} onClick={() => onCorrect(a)}>{t('action.correct')}</button>
          )}
        </li>
      ))}
    </ol>
  )
}

/**
 * Record work done to an asset, or (with `correcting`) replace a record with a corrected one and a reason.
 * `issueId` fixes the issue (issue page); otherwise any OPEN issue of the asset can be chosen.
 */
export function ActionForm({
  ws, assetId, issueId, correcting, onDone, onCancelCorrection,
}: {
  ws: string
  assetId: string
  issueId?: string
  correcting?: ActionRecord | null
  onDone?: () => void
  onCancelCorrection?: () => void
}) {
  const { t, te } = useI18n()
  const record = useRecordAction(ws, assetId)
  const correct = useCorrectAction(ws, assetId)
  const openIssues = useIssues(ws, { asset_id: assetId, is_open: true, limit: 50 })
  const [problem, setProblem] = useState<string | null>(null)
  const key = correcting?.id ?? 'new'

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    const f = new FormData(form)
    const text = (k: string) => String(f.get(k) ?? '').trim()
    const measured = amount(text('quantity'), text('unit'))
    if (measured === 'invalid') return setProblem(t('action.errQuantity'))
    const note = text('note')
    if (correcting && note.length < MIN_REASON) return setProblem(t('action.errReason', { min: MIN_REASON }))
    const days = text('followUp')
    setProblem(null)
    const common = { kind: text('kind') as ActionRecord['kind'], product: text('product') || undefined, performed_at: enteredAt(text('date')), ...measured }
    const done = { onSuccess: () => { form.reset(); onDone?.() } }
    if (correcting) {
      correct.mutate({ ...common, id: correcting.id, note, withdrawn: f.get('withdraw') === 'on' }, done)
    } else {
      const issue = issueId ?? (text('issue') || undefined)
      record.mutate({ ...common, note: note || undefined, issue_id: issue, follow_up_days: days ? Number(days) : undefined }, done)
    }
  }

  const pending = record.isPending || correct.isPending
  const serverError = record.error ?? correct.error
  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-line bg-surface p-3" aria-label={correcting ? t('action.formCorrect') : t('action.formRecord')}>
      {correcting && (
        <p className="text-sm text-ink-2">
          {t('action.correcting', { what: te('actionKind', correcting.kind) })}{' '}
          <button type="button" className="text-moss underline" onClick={onCancelCorrection}>{t('action.cancelCorrection')}</button>
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-4">
        <Field id={`a-kind-${key}`} label={t('action.kind')}>
          <select id={`a-kind-${key}`} name="kind" className={input} defaultValue={correcting?.kind ?? 'treat'} key={`k-${key}`}>
            {ACTION_KINDS.map((k) => <option key={k} value={k}>{te('actionKind', k)}</option>)}
          </select>
        </Field>
        <Field id={`a-product-${key}`} label={t('action.product')}>
          <input id={`a-product-${key}`} name="product" className={input} maxLength={120} defaultValue={correcting?.product ?? ''} key={`p-${key}`} placeholder={t('action.productPlaceholder')} />
        </Field>
        <Field id={`a-qty-${key}`} label={t('action.quantity')}>
          <input id={`a-qty-${key}`} name="quantity" type="number" step="any" min={0} className={input} defaultValue={correcting?.quantity ?? ''} key={`q-${key}`} />
        </Field>
        <Field id={`a-unit-${key}`} label={t('action.unit')}>
          <select id={`a-unit-${key}`} name="unit" className={input} defaultValue={correcting?.unit ?? 'l'} key={`u-${key}`}>
            {ACTION_UNITS.map((u) => <option key={u} value={u}>{te('unit', u)}</option>)}
          </select>
        </Field>
        <Field id={`a-date-${key}`} label={t('action.date')} hint={t('action.dateHint')}>
          <input id={`a-date-${key}`} name="date" type="date" className={input} />
        </Field>
        {!correcting && !issueId && (
          <Field id={`a-issue-${key}`} label={t('action.issue')}>
            <select id={`a-issue-${key}`} name="issue" className={input} defaultValue="">
              <option value="">{t('action.noIssue')}</option>
              {openIssues.data?.items.map((i) => <option key={i.id} value={i.id}>{i.key} · {i.title}</option>)}
            </select>
          </Field>
        )}
        {!correcting && (
          <Field id={`a-follow-${key}`} label={t('action.followUpDays')} hint={t('action.followUpHint')}>
            <input id={`a-follow-${key}`} name="followUp" type="number" min={1} max={90} step={1} className={input} />
          </Field>
        )}
      </div>
      <Field id={`a-note-${key}`} label={correcting ? t('action.reasonRequired') : t('action.noteOptional')}>
        <input id={`a-note-${key}`} name="note" className={input} maxLength={2000} />
      </Field>
      {correcting && (
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="withdraw" /> {t('action.withdraw')}</label>
      )}
      {(problem || serverError) && <p role="alert" className="text-sm text-critical">{problem ?? errorMessage(serverError)}</p>}
      <button type="submit" className={btnPrimary} disabled={pending}>{pending ? t('action.saving') : correcting ? t('action.saveCorrection') : t('action.saveRecord')}</button>
      <p className="text-xs text-ink-3">{t('action.appendOnly')}</p>
    </form>
  )
}

/** The work done to this asset (asset page). Workers record; managers correct. */
export function ActionPanel({ ws, asset, role, show = 'all' }: { ws: string; asset: Asset; role: Role; show?: 'all' | 'history' }) {
  const { t } = useI18n()
  const actions = useActions(ws, asset.id)
  const [correcting, setCorrecting] = useState<ActionRecord | null>(null)
  const canRecord = atLeast(role, 'worker') && asset.is_active
  const isManager = atLeast(role, 'manager')

  if (actions.isLoading) return <LoadingBlock label={t('action.loading')} />
  if (actions.error || !actions.data) return <ErrorState error={actions.error ?? new Error(t('action.unavailable'))} onRetry={() => actions.refetch()} />
  const history = actions.data.history

  return (
    <section aria-labelledby="actions">
      <h2 id="actions" className="mb-2 font-semibold">{t('action.title')}</h2>
      {history.length === 0 ? <p className="mb-3 text-sm text-ink-3">{t('action.none')}</p> : (
        <div className="mb-3"><ActionList ws={ws} actions={history} onCorrect={isManager ? setCorrecting : undefined} /></div>
      )}
      {!asset.is_active && <p className="text-sm text-ink-3">{t('action.exited')}</p>}
      {canRecord && (show === 'all' || correcting) && (
        <ActionForm key={correcting?.id ?? 'new'} ws={ws} assetId={asset.id} correcting={correcting} onDone={() => setCorrecting(null)} onCancelCorrection={() => setCorrecting(null)} />
      )}
    </section>
  )
}
