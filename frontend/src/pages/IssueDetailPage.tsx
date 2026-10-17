import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ProblemError } from '../api/client'
import type { IssueDetail, Workflow } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { Field, PageHeader, SeverityChip, StateChip, TaskStatusChip, btn, btnPrimary, input } from '../components/domain'
import { EvidenceGallery } from '../components/EvidenceGallery'
import { ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { atLeast, fmtDateTime, label, relative, toIsoOrUndefined } from '../lib/format'
import { useCreateTask, useIssue, useTransitionIssue, useWorkflows } from '../lib/slice'
import { useMembers } from '../lib/queries'

const OUTCOMES = ['fixed', 'mitigated', 'no_action_needed', 'duplicate']

function Stepper({ wf, current, visited }: { wf: Workflow; current: string; visited: Set<string> }) {
  // The happy path in order; terminal "won't fix" is shown separately when it is the current state.
  const path = wf.states.filter((s) => s !== 'closed_wont_fix')
  const idx = path.indexOf(current)
  return (
    <ol className="flex flex-wrap items-center gap-1 text-xs" aria-label={`${wf.label} workflow`}>
      {path.map((s, i) => {
        // only stages the issue really passed through get a check mark; skipped stages stay plain
        const state = current === 'closed_wont_fix' ? 'off' : i === idx ? 'now' : i < idx && visited.has(s) ? 'past' : 'next'
        return (
          <li key={s} aria-current={state === 'now' ? 'step' : undefined} className={`rounded border px-2 py-1 ${state === 'now' ? 'border-moss bg-moss font-medium text-moss-ink' : state === 'past' ? 'border-moss text-moss' : 'border-line text-ink-3'}`}>
            {state === 'past' && <span aria-hidden="true">✓ </span>}
            {label(s)}
          </li>
        )
      })}
      {current === 'closed_wont_fix' && <li aria-current="step" className="rounded border border-ink-3 bg-surface-2 px-2 py-1 font-medium">Closed — won't fix</li>}
    </ol>
  )
}

function TransitionPanel({ issue, wf, ws }: { issue: IssueDetail; wf: Workflow; ws: string }) {
  const move = useTransitionIssue(ws, issue.id)
  const [target, setTarget] = useState<string | null>(null)
  const openTasks = issue.tasks.filter((t) => ['todo', 'in_progress', 'blocked'].includes(t.status))
  const terminal = target != null && wf.terminal.includes(target)
  const wontFix = target === 'closed_wont_fix'

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const note = String(f.get('note') ?? '').trim() || undefined
    const body: Record<string, unknown> = { to_state: target, note }
    if (terminal) {
      body.resolution = { outcome: wontFix ? 'wont_fix' : f.get('outcome'), notes: String(f.get('notes') ?? '').trim() || undefined, cancel_open_tasks: f.get('cancel') === 'on' }
    }
    move.mutate(body, { onSuccess: () => setTarget(null) })
  }

  const err = move.error instanceof ProblemError ? move.error : null
  return (
    <section aria-labelledby="mv" className="rounded-lg border border-line bg-surface p-4">
      <h2 id="mv" className="mb-2 font-semibold">Move this issue</h2>
      {issue.allowed_transitions.length === 0 && <p className="text-sm text-ink-3">No further transitions.</p>}
      {target == null ? (
        <div className="flex flex-wrap gap-2">
          {issue.allowed_transitions.map((s) => (
            <button key={s} type="button" className={wf.terminal.includes(s) ? btn : btnPrimary} onClick={() => { move.reset(); setTarget(s) }}>
              {issue.is_open ? (wf.terminal.includes(s) ? (s === 'closed_wont_fix' ? "Close — won't fix" : `Resolve (${label(s)})`) : `→ ${label(s)}`) : `Reopen (${label(s)})`}
            </button>
          ))}
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-3">
          <p className="text-sm">Moving to <strong>{label(target)}</strong></p>
          {terminal && !wontFix && (
            <Field id="outcome" label="Outcome">
              <select id="outcome" name="outcome" className={`${input} max-w-xs`} defaultValue="fixed">{OUTCOMES.map((o) => <option key={o} value={o}>{label(o)}</option>)}</select>
            </Field>
          )}
          {terminal && (
            <Field id="notes" label={wontFix ? 'Why will this not be fixed? (required)' : 'Resolution notes'}>
              <textarea id="notes" name="notes" rows={2} required={wontFix} className={input} />
            </Field>
          )}
          {terminal && openTasks.length > 0 && (
            <label className="flex items-start gap-2 text-sm"><input type="checkbox" name="cancel" className="mt-1" /> Cancel the {openTasks.length} open task(s) ({openTasks.map((t) => t.key).join(', ')}) when closing</label>
          )}
          <Field id="note" label="Note (optional)"><input id="note" name="note" className={input} maxLength={2000} /></Field>
          {err && (
            <p role="alert" className="text-sm text-critical">
              {err.message}
              {err.code === 'open_tasks' && ' Complete the tasks, or tick “cancel open tasks”.'}
            </p>
          )}
          {move.error != null && !err && <p role="alert" className="text-sm text-critical">{errorMessage(move.error)}</p>}
          <div className="flex gap-2"><button className={btnPrimary} disabled={move.isPending}>{move.isPending ? 'Saving…' : 'Confirm'}</button><button type="button" className={btn} onClick={() => setTarget(null)}>Cancel</button></div>
        </form>
      )}
    </section>
  )
}

function AddTask({ issue, ws, canAssign }: { issue: IssueDetail; ws: string; canAssign: boolean }) {
  const create = useCreateTask(ws)
  const members = useMembers(ws)
  const [open, setOpen] = useState(false)
  if (!canAssign || !issue.is_open) return null
  if (!open) return <button type="button" className={btn} onClick={() => setOpen(true)}>Add task</button>
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
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-line bg-surface p-3" aria-label="Add task">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2"><Field id="ttitle" label="Task"><input id="ttitle" name="title" required maxLength={300} className={input} placeholder="e.g. Apply neem-oil spray" /></Field></div>
        <Field id="ttype" label="Type"><select id="ttype" name="type" className={input} defaultValue="treat">{['inspect', 'treat', 'water', 'fertilize', 'prune', 'replace', 'monitor', 'other'].map((t) => <option key={t} value={t}>{label(t)}</option>)}</select></Field>
        <Field id="tprio" label="Priority"><select id="tprio" name="priority" className={input} defaultValue="p3">{['p1', 'p2', 'p3', 'p4'].map((p) => <option key={p} value={p}>{p.toUpperCase()}</option>)}</select></Field>
        <Field id="tass" label="Assign to"><select id="tass" name="assignee" className={input} defaultValue=""><option value="">Unassigned</option>{members.data?.map((m) => <option key={m.user_id} value={m.user_id}>{m.name} ({m.role})</option>)}</select></Field>
        <Field id="tdue" label="Due"><input id="tdue" name="due" type="datetime-local" className={input} /></Field>
      </div>
      {create.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(create.error)}</p>}
      <div className="flex gap-2"><button className={btnPrimary} disabled={create.isPending}>Create task</button><button type="button" className={btn} onClick={() => setOpen(false)}>Cancel</button></div>
    </form>
  )
}

export function IssueDetailPage() {
  const { issueId = '' } = useParams()
  const { ws, workspace } = useWorkspaceCtx()
  const issue = useIssue(ws, issueId)
  const flows = useWorkflows(ws)
  if (issue.isLoading) return <LoadingBlock label="Loading issue" />
  if (issue.error || !issue.data) return <ErrorState error={issue.error ?? new Error('Issue not found')} onRetry={() => issue.refetch()} />
  const i = issue.data
  const wf = flows.data?.find((w) => w.key === i.workflow_key)
  const canManage = atLeast(workspace.role, 'manager')

  return (
    <div className="space-y-6">
      <nav aria-label="Breadcrumb" className="text-sm text-ink-3"><Link to={`/w/${ws}/issues`} className="hover:underline">Issues</Link> / {i.key}</nav>
      <PageHeader title={`${i.key} · ${i.title}`} subtitle={<>{i.asset_id && <Link className="text-moss hover:underline" to={`/w/${ws}/assets/${i.asset_id}`}>{i.asset_label}</Link>} · {label(i.category)} · opened {relative(i.opened_at)} · {i.source === 'agent' ? 'suggested by a rule' : label(i.source)}</>}>
        <SeverityChip severity={i.severity} />
        <StateChip state={i.state} open={i.is_open} />
      </PageHeader>
      {wf && <Stepper wf={wf} current={i.state} visited={new Set(i.history.map((h) => h.to_state))} />}
      {i.description && <p className="max-w-prose text-sm text-ink-2">{i.description}</p>}
      {!i.is_open && (
        <p className="rounded-lg border border-moss bg-surface p-3 text-sm">
          Closed {fmtDateTime(i.resolved_at)} · outcome <strong>{label(i.resolution_outcome ?? '')}</strong>{i.resolution_notes ? ` — ${i.resolution_notes}` : ''}
        </p>
      )}

      {canManage && wf ? <TransitionPanel key={`${i.state}-${i.version}`} issue={i} wf={wf} ws={ws} /> : <p className="text-sm text-ink-3">Only a manager can move an issue through its workflow.</p>}

      <section aria-labelledby="tk">
        <div className="mb-2 flex items-center justify-between gap-2"><h2 id="tk" className="font-semibold">Tasks</h2><AddTask issue={i} ws={ws} canAssign={canManage} /></div>
        {i.tasks.length === 0 ? <p className="text-sm text-ink-3">No tasks yet.</p> : (
          <ul className="space-y-2">{i.tasks.map((t) => (
            <li key={t.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface p-2 text-sm">
              <span className="font-medium">{t.key}</span><span>{t.title}</span><TaskStatusChip status={t.status} overdue={t.overdue} />
              <span className="text-ink-3">{t.due_at ? `due ${relative(t.due_at)}` : 'no due date'}</span>
            </li>))}</ul>
        )}
        <p className="mt-2 text-xs text-ink-3">Update task progress on the <Link className="underline" to={`/w/${ws}/tasks`}>Tasks</Link> page.</p>
      </section>

      <section aria-labelledby="ev">
        <h2 id="ev" className="mb-2 font-semibold">Evidence</h2>
        {i.evidence.length === 0 ? <p className="text-sm text-ink-3">No observations attached.</p> : (
          <ul className="space-y-2">{i.evidence.map((o) => (
            <li key={o.id} className="rounded-lg border border-line bg-surface p-2 text-sm">
              <p className="text-xs text-ink-3">{fmtDateTime(o.observed_at)}</p>
              <p>{[o.health_score != null ? `Health ${Math.round(o.health_score)}` : null, o.symptoms.join(', ') || null, o.notes].filter(Boolean).join(' · ')}</p>
              {o.attachments.map((a) => <p key={a.name + (a.url ?? '')} className="text-xs text-ink-3">Photo: {a.caption ?? a.name}</p>)}
            </li>))}</ul>
        )}
        <h3 className="mb-2 mt-4 text-sm font-semibold">Photos</h3>
        <EvidenceGallery ws={ws} assetId={i.asset_id ?? undefined} issueId={i.id} canUpload={atLeast(workspace.role, 'worker') && i.is_open} isManager={atLeast(workspace.role, 'manager')} />
      </section>

      <section aria-labelledby="hs">
        <h2 id="hs" className="mb-2 font-semibold">History</h2>
        <ol className="space-y-2 border-l border-line pl-4">
          {i.history.map((h, n) => (
            <li key={n} className="text-sm">
              <p className="text-xs text-ink-3">{fmtDateTime(h.at)}</p>
              <p>{h.from_state == null ? <>Opened as <strong>{label(h.to_state)}</strong></> : h.from_state === h.to_state ? <>Updated</> : <>{label(h.from_state)} → <strong>{label(h.to_state)}</strong></>}{h.note ? ` — ${h.note}` : ''}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
