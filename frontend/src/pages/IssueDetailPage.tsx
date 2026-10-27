import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ProblemError } from '../api/client'
import type { IssueDetail, Workflow } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { Field, SeverityChip, StateChip, TaskStatusChip, btn, btnPrimary, input } from '../components/domain'
import { Icon } from '../components/icons'
import { Card, SectionHeading, Tag } from '../components/ui'
import { systemNote } from '../lib/recText'
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

/**
 * The workflow as numbered steps (ADR-080). Only stages the issue really passed through get a check mark; skipped
 * stages stay plain; "won't fix" is shown on its own when the issue was closed that way.
 */
function Stepper({ wf, current, visited }: { wf: Workflow; current: string; visited: Set<string> }) {
  const { t, te } = useI18n()
  const path = wf.states.filter((s) => s !== 'closed_wont_fix')
  const idx = path.indexOf(current)
  return (
    <ol className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-line bg-surface px-4 py-3" aria-label={t('issue.workflow', { name: te('workflow', wf.key, wf.label) })}>
      {path.map((s, i) => {
        const state = current === 'closed_wont_fix' ? 'off' : i === idx ? 'now' : i < idx && visited.has(s) ? 'past' : 'next'
        return (
          <li key={s} aria-current={state === 'now' ? 'step' : undefined} className="flex items-center gap-3">
            {i > 0 && <span aria-hidden="true" className={`hidden h-[1.5px] w-8 sm:block ${state === 'past' || state === 'now' ? 'bg-moss' : 'bg-line'}`} />}
            <span className={`flex items-center gap-2 text-sm ${state === 'now' ? 'font-semibold text-ink' : state === 'past' ? 'text-ink' : 'text-ink-2'}`}>
              <b className={`flex h-6 w-6 items-center justify-center rounded-full border-[1.5px] font-mono text-[11px] font-medium ${state === 'now' ? 'border-moss bg-moss text-moss-ink' : state === 'past' ? 'border-moss text-moss' : 'border-line bg-surface'}`}>
                {state === 'past' ? <span aria-hidden="true">✓</span> : i + 1}
              </b>
              {te('issueState', s)}
            </span>
          </li>
        )
      })}
      {current === 'closed_wont_fix' && <li aria-current="step" className="ml-auto rounded border border-ink-3 bg-surface-2 px-2 py-1 text-sm font-semibold">{te('issueState', 'closed_wont_fix')}</li>}
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
    <section aria-labelledby="mv" className="rounded-lg border border-line bg-surface px-4 py-3.5">
      <SectionHeading id="mv" title={t('issue.move')} />
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
  if (!open) return <button type="button" className={btn} onClick={() => setOpen(true)}><Icon name="add" size={16} />{t('issue.addTask')}</button>
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
    <form onSubmit={submit} className="mt-2 w-full space-y-3 rounded-lg border border-line bg-surface p-4 text-left" aria-label={t('issue.addTask')}>
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
      <SectionHeading id="wk" title={t('action.workOnIssue')}>
        {can && !open && <button type="button" className={btn} onClick={() => setOpen(true)}><Icon name="record" size={16} />{t('action.recordWork')}</button>}
      </SectionHeading>
      {issue.actions.length === 0 ? <p className="text-sm text-ink-2">{t('action.noneOnIssue')}</p> : <ActionList ws={ws} actions={issue.actions} />}
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
  const members = useMembers(ws)
  if (issue.isLoading) return <LoadingBlock label={t('issue.loading')} />
  if (issue.error || !issue.data) return <ErrorState error={issue.error ?? new Error(t('issue.notFound'))} onRetry={() => issue.refetch()} />
  const i = issue.data
  const wf = flows.data?.find((w) => w.key === i.workflow_key)
  const canManage = atLeast(workspace.role, 'manager')
  const who = (id: string | null) => (id ? members.data?.find((m) => m.user_id === id)?.name : undefined)

  return (
    <div className="flex flex-col gap-5">
      <nav aria-label={t('asset.breadcrumb')} className="text-[13px] text-ink-2">
        <Link to={`/w/${ws}/issues`} className="text-moss hover:underline">{t('issues.caption')}</Link> / {i.key}
      </nav>
      <header className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <Tag>{i.key}</Tag>
          <SeverityChip severity={i.severity} />
          <StateChip state={i.state} open={i.is_open} />
          <Tag>{te('issueCategory', i.category)}</Tag>
        </div>
        <h1 className="text-[32px] leading-tight font-bold">{i.title}</h1>
        <p className="text-sm text-ink-2">
          {t('issue.opened', { when: fmt.relative(i.opened_at) })}
          {who(i.reporter_id) && <> · {t('issue.by', { name: who(i.reporter_id)! })}</>}
          {i.asset_id && <> · <Link className="text-moss hover:underline" to={`/w/${ws}/assets/${i.asset_id}`}>{i.asset_label}</Link></>}
        </p>
      </header>

      {wf && <Stepper wf={wf} current={i.state} visited={new Set(i.history.map((h) => h.to_state))} />}

      {!i.is_open && (
        <p className="rounded-lg border border-moss/40 bg-moss-soft px-4 py-3 text-sm">
          {t('issue.closedOn', { when: fmt.dateTime(i.resolved_at) })} <strong>{te('outcome', i.resolution_outcome ?? '')}</strong>{i.resolution_notes ? ` — ${i.resolution_notes}` : ''}
        </p>
      )}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-5">
          {i.description && <p className="max-w-[62ch] text-base">{i.description}</p>}
          <VerificationCard v={i.verification} />
          {canManage && wf ? <TransitionPanel key={`${i.state}-${i.version}`} issue={i} wf={wf} ws={ws} /> : <p className="text-sm text-ink-2">{t('issue.onlyManager')}</p>}

          <section aria-labelledby="tk">
            <SectionHeading id="tk" title={t('issue.tasks')}><AddTask issue={i} ws={ws} canAssign={canManage} /></SectionHeading>
            {i.tasks.length === 0 ? <p className="text-sm text-ink-2">{t('issue.noTasks')}</p> : (
              <ul className="overflow-hidden rounded-lg border border-line bg-surface">
                {i.tasks.map((task) => (
                  <li key={task.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line-soft px-3.5 py-2.5 text-sm last:border-0">
                    <Tag tone={task.overdue ? 'critical' : 'neutral'}>{task.key}</Tag>
                    <span className="min-w-0 flex-1">{task.title}</span>
                    {who(task.assignee_id) && <span className="text-ink-2">{who(task.assignee_id)}</span>}
                    <TaskStatusChip status={task.status} overdue={task.overdue} />
                    <span className={`font-mono text-xs ${task.overdue ? 'text-critical' : 'text-ink-2'}`}>{task.due_at ? t('tasks.due', { when: fmt.relative(task.due_at) }) : t('tasks.noDue')}</span>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-2 text-xs text-ink-2">{t('issue.updateOnTasks')} <Link className="underline" to={`/w/${ws}/tasks`}>{t('issue.tasksPage')}</Link> {t('issue.page')}</p>
          </section>

          <IssueWork issue={i} ws={ws} canRecord={atLeast(workspace.role, 'worker')} />

          <section aria-labelledby="ev">
            <SectionHeading id="ev" title={t('issue.evidence')} />
            {i.evidence.length === 0 ? <p className="text-sm text-ink-2">{t('issue.noEvidence')}</p> : (
              <ul className="overflow-hidden rounded-lg border border-line bg-surface">
                {i.evidence.map((o) => (
                  <li key={o.id} className="flex gap-3 border-b border-line-soft px-3.5 py-2.5 text-sm last:border-0">
                    <span className="w-28 shrink-0 font-mono text-xs text-ink-2">{fmt.dateTime(o.observed_at)}</span>
                    <span className="min-w-0">
                      {[o.health_score != null ? t('issue.healthN', { n: Math.round(o.health_score) }) : null, o.symptoms.join(', ') || null, o.notes].filter(Boolean).join(' · ')}
                      {o.attachments.map((a) => <span key={a.name + (a.url ?? '')} className="block text-xs text-ink-2">{t('issue.photoRef', { name: a.caption ?? a.name })}</span>)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <h3 className="mt-4 mb-2 text-[17px] font-semibold">{t('issue.photos')}</h3>
            <EvidenceGallery ws={ws} assetId={i.asset_id ?? undefined} issueId={i.id} canUpload={atLeast(workspace.role, 'worker') && i.is_open} isManager={atLeast(workspace.role, 'manager')} />
          </section>
        </div>

        <aside className="flex flex-col gap-3.5">
          <Card className="px-4 py-3.5">
            <section aria-labelledby="det">
              <SectionHeading id="det" title={t('issue.details')} />
              <dl className="grid grid-cols-[96px_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm">
                {i.asset_id && <><dt className="text-ink-2">{t('issues.col.asset')}</dt><dd><Link className="text-moss hover:underline" to={`/w/${ws}/assets/${i.asset_id}`}>{i.asset_label}</Link></dd></>}
                <dt className="text-ink-2">{t('issue.category')}</dt><dd>{te('issueCategory', i.category)}</dd>
                <dt className="text-ink-2">{t('issues.col.severity')}</dt><dd>{te('severity', i.severity)}</dd>
                <dt className="text-ink-2">{t('issue.source')}</dt><dd>{te('issueSource', i.source)}</dd>
                {wf && <><dt className="text-ink-2">{t('issue.workflowName')}</dt><dd>{te('workflow', wf.key, wf.label)}</dd></>}
                <dt className="text-ink-2">{t('issues.col.opened')}</dt><dd className="font-mono text-xs leading-5">{fmt.dateTime(i.opened_at)}</dd>
                {who(i.assignee_id) && <><dt className="text-ink-2">{t('issue.assignee')}</dt><dd>{who(i.assignee_id)}</dd></>}
              </dl>
            </section>
          </Card>
          <Card className="px-4 py-3.5">
            <section aria-labelledby="hs">
              <SectionHeading id="hs" title={t('issue.history')} />
              <ol className="flex flex-col gap-2.5">
                {[...i.history].reverse().map((h, n) => (
                  <li key={n} className="grid grid-cols-[88px_minmax(0,1fr)] gap-2 text-sm">
                    <span className="font-mono text-xs leading-5 text-ink-2">{fmt.dateTime(h.at)}</span>
                    <span>
                      {h.from_state == null ? <>{t('issue.openedAs')} <strong>{te('issueState', h.to_state)}</strong></> : h.from_state === h.to_state ? <>{t('issue.updated')}</> : <>{te('issueState', h.from_state)} → <strong>{te('issueState', h.to_state)}</strong></>}
                      {who(h.actor_id) && <span className="text-ink-2"> · {who(h.actor_id)}</span>}
                      {h.note && <span className="block text-ink-2">{systemNote(h.note, t)}</span>}
                    </span>
                  </li>
                ))}
              </ol>
            </section>
          </Card>
        </aside>
      </div>
    </div>
  )
}
