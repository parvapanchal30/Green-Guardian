import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ProblemError } from '../api/client'
import type { IssueDetail, Workflow } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { Field, PageHeader, SeverityChip, StateChip, TaskStatusChip, btn, btnPrimary, input } from '../components/domain'
import { ActionForm, ActionList } from '../components/ActionPanel'
import { EvidenceGallery } from '../components/EvidenceGallery'
import { VerificationCard } from '../components/VerificationCard'
import { ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { useI18n } from '../i18n'
import { atLeast, toIsoOrUndefined } from '../lib/format'
import { useCreateTask, useIssue, useTransitionIssue, useWorkflows } from '../lib/slice'
import { useMembers } from '../lib/queries'

const OUTCOMES = ['fixed', 'mitigated', 'no_action_needed', 'duplicate']
const SUCCESS = new Set(['fixed', 'mitigated'])
const TASK_TYPES = ['inspect', 'treat', 'water', 'fertilize', 'prune', 'replace', 'monitor', 'other']

function Stepper({ wf, current, visited }: { wf: Workflow; current: string; visited: Set<string> }) {
  const { t, te } = useI18n()
  // The happy path in order; terminal "won't fix" is shown separately when it is the current state.
  const path = wf.states.filter((s) => s !== 'closed_wont_fix')
  const idx = path.indexOf(current)
  return (
    <ol className="flex flex-wrap items-center gap-1 text-xs" aria-label={t('issue.workflow', { name: wf.label })}>
      {path.map((s, i) => {
        // only stages the issue really passed through get a check mark; skipped stages stay plain
        const state = current === 'closed_wont_fix' ? 'off' : i === idx ? 'now' : i < idx && visited.has(s) ? 'past' : 'next'
        return (
          <li key={s} aria-current={state === 'now' ? 'step' : undefined} className={`rounded border px-2 py-1 ${state === 'now' ? 'border-moss bg-moss font-medium text-moss-ink' : state === 'past' ? 'border-moss text-moss' : 'border-line text-ink-3'}`}>
            {state === 'past' && <span aria-hidden="true">✓ </span>}
            {te('issueState', s)}
          </li>
        )
      })}
      {current === 'closed_wont_fix' && <li aria-current="step" className="rounded border border-ink-3 bg-surface-2 px-2 py-1 font-medium">{te('issueState', 'closed_wont_fix')}</li>}
    </ol>
  )
}

function TransitionPanel({ issue, wf, ws }: { issue: IssueDetail; wf: Workflow; ws: string }) {
  const { t, te } = useI18n()
  const move = useTransitionIssue(ws, issue.id)
  const [target, setTarget] = useState<string | null>(null)
  const [outcome, setOutcome] = useState('fixed')
  const [problem, setProblem] = useState<string | null>(null)
  const openTasks = issue.tasks.filter((task) => ['todo', 'in_progress', 'blocked'].includes(task.status))
  const terminal = target != null && wf.terminal.includes(target)
  const wontFix = target === 'closed_wont_fix'
  // Closing a plant issue as fixed or mitigated needs a look at the asset after the last work (ADR-059).
  const askFollowUp = terminal && !wontFix && SUCCESS.has(outcome) && issue.verification.required_for_success
  const followUpNeeded = askFollowUp && issue.verification.status === 'awaiting_follow_up'

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const note = String(f.get('note') ?? '').trim() || undefined
    const body: Record<string, unknown> = { to_state: target, note }
    if (terminal) {
      const resolution: Record<string, unknown> = { outcome: wontFix ? 'wont_fix' : f.get('outcome'), notes: String(f.get('notes') ?? '').trim() || undefined, cancel_open_tasks: f.get('cancel') === 'on' }
      if (askFollowUp) {
        const score = String(f.get('fscore') ?? '').trim()
        const seen = String(f.get('fnotes') ?? '').trim()
        if (score !== '' || seen) resolution.follow_up = { health_score: score === '' ? undefined : Number(score), notes: seen || undefined }
        else if (followUpNeeded) return setProblem(t('verify.needFollowUp'))
      }
      body.resolution = resolution
    }
    setProblem(null)
    move.mutate(body, { onSuccess: () => setTarget(null) })
  }

  const buttonText = (s: string) => {
    const state = te('issueState', s)
    if (!issue.is_open) return t('issue.reopenTo', { state })
    if (!wf.terminal.includes(s)) return t('issue.moveTo', { state })
    return s === 'closed_wont_fix' ? t('issue.closeWontFix') : t('issue.resolveTo', { state })
  }

  const err = move.error instanceof ProblemError ? move.error : null
  return (
    <section aria-labelledby="mv" className="rounded-lg border border-line bg-surface p-4">
      <h2 id="mv" className="mb-2 font-semibold">{t('issue.move')}</h2>
      {issue.allowed_transitions.length === 0 && <p className="text-sm text-ink-3">{t('issue.noTransitions')}</p>}
      {target == null ? (
        <div className="flex flex-wrap gap-2">
          {issue.allowed_transitions.map((s) => (
            <button key={s} type="button" className={wf.terminal.includes(s) ? btn : btnPrimary} onClick={() => { move.reset(); setTarget(s) }}>
              {buttonText(s)}
            </button>
          ))}
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-3">
          <p className="text-sm">{t('issue.movingTo')} <strong>{te('issueState', target)}</strong></p>
          {terminal && !wontFix && (
            <Field id="outcome" label={t('issue.outcome')}>
              <select id="outcome" name="outcome" className={`${input} max-w-xs`} value={outcome} onChange={(e) => setOutcome(e.target.value)}>{OUTCOMES.map((o) => <option key={o} value={o}>{te('outcome', o)}</option>)}</select>
            </Field>
          )}
          {terminal && (
            <Field id="notes" label={wontFix ? t('issue.whyNotFixed') : t('issue.resolutionNotes')}>
              <textarea id="notes" name="notes" rows={2} required={wontFix} className={input} />
            </Field>
          )}
          {askFollowUp && (
            <fieldset className="grid gap-2 rounded border border-line p-2 sm:grid-cols-2">
              <legend className="px-1 text-xs text-ink-3">{followUpNeeded ? t('verify.followUpRequired') : t('verify.followUpOptional')}</legend>
              <Field id="fscore" label={t('tasks.scoreNow')}><input id="fscore" name="fscore" type="number" min={0} max={100} step="any" className={input} /></Field>
              <Field id="fnotes" label={t('tasks.observed')}><input id="fnotes" name="fnotes" className={input} maxLength={5000} /></Field>
            </fieldset>
          )}
          {terminal && openTasks.length > 0 && (
            <label className="flex items-start gap-2 text-sm"><input type="checkbox" name="cancel" className="mt-1" /> {t('issue.cancelOpenTasks', { count: openTasks.length, keys: openTasks.map((task) => task.key).join(', ') })}</label>
          )}
          <Field id="note" label={t('issue.noteOptional')}><input id="note" name="note" className={input} maxLength={2000} /></Field>
          {problem && <p role="alert" className="text-sm text-critical">{problem}</p>}
          {err && (
            <p role="alert" className="text-sm text-critical">
              {err.message}
              {err.code === 'open_tasks' && t('issue.openTasksHint')}
            </p>
          )}
          {move.error != null && !err && <p role="alert" className="text-sm text-critical">{errorMessage(move.error)}</p>}
          <div className="flex gap-2"><button className={btnPrimary} disabled={move.isPending}>{move.isPending ? t('issue.saving') : t('issue.confirm')}</button><button type="button" className={btn} onClick={() => { setTarget(null); setProblem(null) }}>{t('issue.cancel')}</button></div>
        </form>
      )}
    </section>
  )
}

function AddTask({ issue, ws, canAssign }: { issue: IssueDetail; ws: string; canAssign: boolean }) {
  const { t, te } = useI18n()
  const create = useCreateTask(ws)
  const members = useMembers(ws)
  const [open, setOpen] = useState(false)
  if (!canAssign || !issue.is_open) return null
  if (!open) return <button type="button" className={btn} onClick={() => setOpen(true)}>{t('issue.addTask')}</button>
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    create.mutate(
      {
        title: String(f.get('title')).trim(), type: f.get('type'), priority: f.get('priority'), issue_id: issue.id,
        assignee_id: String(f.get('assignee') ?? '') || undefined, due_at: toIsoOrUndefined(String(f.get('due') ?? '')),
      },
      { onSuccess: () => setOpen(false) },
    )
  }
  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-line bg-surface p-3" aria-label={t('issue.addTask')}>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2"><Field id="ttitle" label={t('issue.task')}><input id="ttitle" name="title" required maxLength={300} className={input} placeholder={t('issue.taskPlaceholder')} /></Field></div>
        <Field id="ttype" label={t('issue.type')}><select id="ttype" name="type" className={input} defaultValue="treat">{TASK_TYPES.map((k) => <option key={k} value={k}>{te('taskType', k)}</option>)}</select></Field>
        <Field id="tprio" label={t('issue.priority')}><select id="tprio" name="priority" className={input} defaultValue="p3">{['p1', 'p2', 'p3', 'p4'].map((p) => <option key={p} value={p}>{p.toUpperCase()}</option>)}</select></Field>
        <Field id="tass" label={t('issue.assignTo')}><select id="tass" name="assignee" className={input} defaultValue=""><option value="">{t('issue.unassigned')}</option>{members.data?.map((m) => <option key={m.user_id} value={m.user_id}>{m.name} ({te('role', m.role)})</option>)}</select></Field>
        <Field id="tdue" label={t('issue.due')}><input id="tdue" name="due" type="datetime-local" className={input} /></Field>
      </div>
      {create.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(create.error)}</p>}
      <div className="flex gap-2"><button className={btnPrimary} disabled={create.isPending}>{t('issue.createTask')}</button><button type="button" className={btn} onClick={() => setOpen(false)}>{t('issue.cancel')}</button></div>
    </form>
  )
}

function IssueWork({ issue, ws, canRecord }: { issue: IssueDetail; ws: string; canRecord: boolean }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  if (!issue.asset_id) return null
  const can = canRecord && issue.is_open
  return (
    <section aria-labelledby="wk">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 id="wk" className="font-semibold">{t('action.workOnIssue')}</h2>
        {can && !open && <button type="button" className={btn} onClick={() => setOpen(true)}>{t('action.recordWork')}</button>}
      </div>
      {issue.actions.length === 0 ? <p className="text-sm text-ink-3">{t('action.noneOnIssue')}</p> : <ActionList ws={ws} actions={issue.actions} />}
      {can && open && (
        <div className="mt-3">
          <ActionForm ws={ws} assetId={issue.asset_id} issueId={issue.id} onDone={() => setOpen(false)} />
          <button type="button" className={`${btn} mt-2`} onClick={() => setOpen(false)}>{t('issue.cancel')}</button>
        </div>
      )}
    </section>
  )
}

export function IssueDetailPage() {
  const { issueId = '' } = useParams()
  const { ws, workspace } = useWorkspaceCtx()
  const { t, te, fmt } = useI18n()
  const issue = useIssue(ws, issueId)
  const flows = useWorkflows(ws)
  if (issue.isLoading) return <LoadingBlock label={t('issue.loading')} />
  if (issue.error || !issue.data) return <ErrorState error={issue.error ?? new Error(t('issue.notFound'))} onRetry={() => issue.refetch()} />
  const i = issue.data
  const wf = flows.data?.find((w) => w.key === i.workflow_key)
  const canManage = atLeast(workspace.role, 'manager')

  return (
    <div className="space-y-6">
      <nav aria-label={t('asset.breadcrumb')} className="text-sm text-ink-3"><Link to={`/w/${ws}/issues`} className="hover:underline">{t('issues.caption')}</Link> / {i.key}</nav>
      <PageHeader title={`${i.key} · ${i.title}`} subtitle={<>{i.asset_id && <Link className="text-moss hover:underline" to={`/w/${ws}/assets/${i.asset_id}`}>{i.asset_label}</Link>} · {te('issueCategory', i.category)} · {t('issue.opened', { when: fmt.relative(i.opened_at) })} · {te('issueSource', i.source)}</>}>
        <SeverityChip severity={i.severity} />
        <StateChip state={i.state} open={i.is_open} />
      </PageHeader>
      {wf && <Stepper wf={wf} current={i.state} visited={new Set(i.history.map((h) => h.to_state))} />}
      {i.description && <p className="max-w-prose text-sm text-ink-2">{i.description}</p>}
      {!i.is_open && (
        <p className="rounded-lg border border-moss bg-surface p-3 text-sm">
          {t('issue.closedOn', { when: fmt.dateTime(i.resolved_at) })} <strong>{te('outcome', i.resolution_outcome ?? '')}</strong>{i.resolution_notes ? ` — ${i.resolution_notes}` : ''}
        </p>
      )}

      <VerificationCard v={i.verification} />

      {canManage && wf ? <TransitionPanel key={`${i.state}-${i.version}`} issue={i} wf={wf} ws={ws} /> : <p className="text-sm text-ink-3">{t('issue.onlyManager')}</p>}

      <section aria-labelledby="tk">
        <div className="mb-2 flex items-center justify-between gap-2"><h2 id="tk" className="font-semibold">{t('issue.tasks')}</h2><AddTask issue={i} ws={ws} canAssign={canManage} /></div>
        {i.tasks.length === 0 ? <p className="text-sm text-ink-3">{t('issue.noTasks')}</p> : (
          <ul className="space-y-2">{i.tasks.map((task) => (
            <li key={task.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface p-2 text-sm">
              <span className="font-medium">{task.key}</span><span>{task.title}</span><TaskStatusChip status={task.status} overdue={task.overdue} />
              <span className="text-ink-3">{task.due_at ? t('tasks.due', { when: fmt.relative(task.due_at) }) : t('tasks.noDue')}</span>
            </li>))}</ul>
        )}
        <p className="mt-2 text-xs text-ink-3">{t('issue.updateOnTasks')} <Link className="underline" to={`/w/${ws}/tasks`}>{t('issue.tasksPage')}</Link> {t('issue.page')}</p>
      </section>

      <IssueWork issue={i} ws={ws} canRecord={atLeast(workspace.role, 'worker')} />

      <section aria-labelledby="ev">
        <h2 id="ev" className="mb-2 font-semibold">{t('issue.evidence')}</h2>
        {i.evidence.length === 0 ? <p className="text-sm text-ink-3">{t('issue.noEvidence')}</p> : (
          <ul className="space-y-2">{i.evidence.map((o) => (
            <li key={o.id} className="rounded-lg border border-line bg-surface p-2 text-sm">
              <p className="text-xs text-ink-3">{fmt.dateTime(o.observed_at)}</p>
              <p>{[o.health_score != null ? t('issue.healthN', { n: Math.round(o.health_score) }) : null, o.symptoms.join(', ') || null, o.notes].filter(Boolean).join(' · ')}</p>
              {o.attachments.map((a) => <p key={a.name + (a.url ?? '')} className="text-xs text-ink-3">{t('issue.photoRef', { name: a.caption ?? a.name })}</p>)}
            </li>))}</ul>
        )}
        <h3 className="mb-2 mt-4 text-sm font-semibold">{t('issue.photos')}</h3>
        <EvidenceGallery ws={ws} assetId={i.asset_id ?? undefined} issueId={i.id} canUpload={atLeast(workspace.role, 'worker') && i.is_open} isManager={atLeast(workspace.role, 'manager')} />
      </section>

      <section aria-labelledby="hs">
        <h2 id="hs" className="mb-2 font-semibold">{t('issue.history')}</h2>
        <ol className="space-y-2 border-l border-line pl-4">
          {i.history.map((h, n) => (
            <li key={n} className="text-sm">
              <p className="text-xs text-ink-3">{fmt.dateTime(h.at)}</p>
              <p>{h.from_state == null ? <>{t('issue.openedAs')} <strong>{te('issueState', h.to_state)}</strong></> : h.from_state === h.to_state ? <>{t('issue.updated')}</> : <>{te('issueState', h.from_state)} → <strong>{te('issueState', h.to_state)}</strong></>}{h.note ? ` — ${h.note}` : ''}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
