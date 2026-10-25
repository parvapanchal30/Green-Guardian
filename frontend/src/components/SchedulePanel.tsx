import { useState, type FormEvent } from 'react'
import type { Asset, InspectionSchedule, Role } from '../api/types'
import { useI18n } from '../i18n'
import { atLeast } from '../lib/format'
import { enteredAt } from '../lib/lifecycle'
import { useMembers } from '../lib/queries'
import { days, useCreateSchedule, useGenerateDue, useSchedule, useSchedules, useUpdateSchedule } from '../lib/schedules'
import { Field, btn, btnPrimary, input } from './domain'
import { ErrorState, LoadingBlock, errorMessage } from './states'
import { StatusChip } from './StatusChip'

/** What each due date of a schedule produced, newest first. */
function History({ ws, id }: { ws: string; id: string }) {
  const { t, te, fmt } = useI18n()
  const q = useSchedule(ws, id)
  if (q.isLoading) return <LoadingBlock label={t('schedule.loadingHistory')} />
  if (!q.data) return null
  if (q.data.occurrences.length === 0) return <p className="text-xs text-ink-3">{t('schedule.noHistory')}</p>
  return (
    <ol aria-label={t('schedule.history')} className="mt-1 space-y-0.5 text-xs text-ink-2">
      {q.data.occurrences.map((o) => (
        <li key={o.due_at}>
          {fmt.date(o.due_at)} · {te('scheduleOutcome', o.outcome)}
          {o.task_key && <> · {o.task_key} ({te('taskStatus', o.task_status ?? '')})</>}
          {o.missed > 0 && <> · {t('schedule.missed', { count: o.missed })}</>}
        </li>
      ))}
    </ol>
  )
}

function Row({ ws, s, isManager }: { ws: string; s: InspectionSchedule; isManager: boolean }) {
  const { t, te, fmt } = useI18n()
  const update = useUpdateSchedule(ws)
  const members = useMembers(ws)
  const [open, setOpen] = useState(false)
  const who = members.data?.find((m) => m.user_id === s.assignee_id)?.name
  return (
    <li className="rounded-lg border border-line bg-surface p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{s.title}</span>
        <StatusChip tone={s.active ? 'live' : 'neutral'}>{s.active ? t('schedule.active') : t('schedule.paused')}</StatusChip>
        <span>{t('schedule.every', { count: s.interval_days })}</span>
        <span className="text-ink-2">{te('taskType', s.task_type)}</span>
        {s.active && <span className="text-ink-2">{t('schedule.nextDue', { when: fmt.date(s.next_due_at) })}</span>}
        {s.lead_days > 0 && <span className="text-xs text-ink-3">{t('schedule.lead', { count: s.lead_days })}</span>}
        {who && <span className="text-ink-2">{t('schedule.assignedTo', { name: who })}</span>}
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" className={`${btn} px-2 py-0.5 text-xs`} aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {open ? t('schedule.hideHistory') : t('schedule.showHistory')}
        </button>
        {isManager && (
          <button type="button" className={`${btn} px-2 py-0.5 text-xs`} disabled={update.isPending} onClick={() => update.mutate({ id: s.id, active: !s.active })}>
            {s.active ? t('schedule.pause') : t('schedule.resume')}
          </button>
        )}
      </div>
      {open && <History ws={ws} id={s.id} />}
      {update.error != null && <p role="alert" className="mt-1 text-sm text-critical">{errorMessage(update.error)}</p>}
    </li>
  )
}

function CreateForm({ ws, asset, onDone }: { ws: string; asset: Asset; onDone: () => void }) {
  const { t, te } = useI18n()
  const create = useCreateSchedule(ws)
  const members = useMembers(ws)
  const [problem, setProblem] = useState<string | null>(null)

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const text = (k: string) => String(f.get(k) ?? '').trim()
    const interval = days(text('interval'), 365)
    const lead = text('lead') === '' ? 0 : days(text('lead'), 30, 0)
    if (interval == null) return setProblem(t('schedule.errInterval'))
    if (lead == null || lead >= interval) return setProblem(t('schedule.errLead'))
    setProblem(null)
    create.mutate(
      {
        asset_id: asset.id,
        title: text('title') || undefined,
        task_type: text('type') as 'inspect' | 'monitor',
        interval_days: interval,
        lead_days: lead,
        first_due_at: enteredAt(text('first')),
        assignee_id: text('assignee') || undefined,
        priority: text('priority') || undefined,
      },
      { onSuccess: onDone },
    )
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-line bg-surface p-3" aria-label={t('schedule.form')}>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="sm:col-span-3">
          <Field id="sc-title" label={t('schedule.title')}>
            <input id="sc-title" name="title" className={input} maxLength={200} placeholder={t('schedule.titlePlaceholder', { label: asset.label })} />
          </Field>
        </div>
        <Field id="sc-type" label={t('schedule.type')}>
          <select id="sc-type" name="type" className={input} defaultValue="inspect">
            {(['inspect', 'monitor'] as const).map((k) => <option key={k} value={k}>{te('taskType', k)}</option>)}
          </select>
        </Field>
        <Field id="sc-interval" label={t('schedule.interval')}>
          <input id="sc-interval" name="interval" type="number" min={1} max={365} step={1} className={input} defaultValue={30} required />
        </Field>
        <Field id="sc-lead" label={t('schedule.leadLabel')} hint={t('schedule.leadHint')}>
          <input id="sc-lead" name="lead" type="number" min={0} max={30} step={1} className={input} defaultValue={0} />
        </Field>
        <Field id="sc-first" label={t('schedule.first')} hint={t('schedule.firstHint')}>
          <input id="sc-first" name="first" type="date" className={input} />
        </Field>
        <Field id="sc-assignee" label={t('issue.assignTo')}>
          <select id="sc-assignee" name="assignee" className={input} defaultValue="">
            <option value="">{t('issue.unassigned')}</option>
            {members.data?.map((m) => <option key={m.user_id} value={m.user_id}>{m.name} ({te('role', m.role)})</option>)}
          </select>
        </Field>
        <Field id="sc-priority" label={t('issue.priority')}>
          <select id="sc-priority" name="priority" className={input} defaultValue="p3">{['p1', 'p2', 'p3', 'p4'].map((p) => <option key={p} value={p}>{p.toUpperCase()}</option>)}</select>
        </Field>
      </div>
      {(problem || create.error != null) && <p role="alert" className="text-sm text-critical">{problem ?? errorMessage(create.error)}</p>}
      <div className="flex gap-2">
        <button type="submit" className={btnPrimary} disabled={create.isPending}>{create.isPending ? t('action.saving') : t('schedule.save')}</button>
        <button type="button" className={btn} onClick={onDone}>{t('issue.cancel')}</button>
      </div>
    </form>
  )
}

/** Recurring inspections of one asset (asset page). Everyone sees them; a manager sets them up, pauses or resumes them. */
export function SchedulePanel({ ws, asset, role }: { ws: string; asset: Asset; role: Role }) {
  const { t } = useI18n()
  const list = useSchedules(ws, { asset_id: asset.id })
  const generate = useGenerateDue(ws)
  const [adding, setAdding] = useState(false)
  const isManager = atLeast(role, 'manager')

  if (list.isLoading) return <LoadingBlock label={t('schedule.loading')} />
  if (list.error || !list.data) return <ErrorState error={list.error ?? new Error(t('schedule.unavailable'))} onRetry={() => list.refetch()} />

  return (
    <section aria-labelledby="schedules">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 id="schedules" className="font-semibold">{t('schedule.panelTitle')}</h2>
        {isManager && (
          <div className="flex gap-2">
            {list.data.some((s) => s.active) && (
              <button type="button" className={btn} disabled={generate.isPending} onClick={() => generate.mutate(undefined as never)}>{t('schedule.generate')}</button>
            )}
            {asset.is_active && !adding && <button type="button" className={btn} onClick={() => setAdding(true)}>{t('schedule.add')}</button>}
          </div>
        )}
      </div>
      {generate.data && <p role="status" className="mb-2 text-sm text-ink-2">{t('schedule.generated', { count: generate.data.created })}</p>}
      {generate.error != null && <p role="alert" className="mb-2 text-sm text-critical">{errorMessage(generate.error)}</p>}
      {list.data.length === 0 && !adding && <p className="text-sm text-ink-3">{t('schedule.none')}</p>}
      <ul className="space-y-2">{list.data.map((s) => <Row key={`${s.id}-${s.version}`} ws={ws} s={s} isManager={isManager} />)}</ul>
      {adding && <div className="mt-3"><CreateForm ws={ws} asset={asset} onDone={() => setAdding(false)} /></div>}
      <p className="mt-2 text-xs text-ink-3">{t('schedule.explain')}</p>
    </section>
  )
}
