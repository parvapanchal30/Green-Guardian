import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import type { Task } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { Field, PageHeader, Pagination, TaskStatusChip, btn, btnPrimary, input } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { atLeast, label, relative } from '../lib/format'
import { useMembers } from '../lib/queries'
import { useTasks, useTransitionTask } from '../lib/slice'
import { useAuth } from '../lib/auth'

const PAGE = 25
const NEXT: Record<string, { to: string; text: string }[]> = {
  todo: [{ to: 'in_progress', text: 'Start' }, { to: 'done', text: 'Complete' }],
  in_progress: [{ to: 'done', text: 'Complete' }, { to: 'blocked', text: 'Blocked' }],
  blocked: [{ to: 'in_progress', text: 'Resume' }],
  done: [{ to: 'in_progress', text: 'Reopen' }],
  cancelled: [{ to: 'todo', text: 'Reopen' }],
}

function Row({ t, ws, canMove, isManager }: { t: Task; ws: string; canMove: boolean; isManager: boolean }) {
  const move = useTransitionTask(ws)
  const [completing, setCompleting] = useState(false)
  const members = useMembers(ws)
  const who = members.data?.find((m) => m.user_id === t.assignee_id)?.name ?? (t.assignee_id ? 'Assigned' : 'Unassigned')
  const reopening = t.status === 'done' || t.status === 'cancelled'

  function complete(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const score = String(f.get('score') ?? '').trim()
    const notes = String(f.get('fnotes') ?? '').trim()
    const body: Record<string, unknown> = { to_status: 'done', note: String(f.get('note') ?? '').trim() || undefined }
    if (t.asset_id && (score !== '' || notes)) body.observation = { health_score: score === '' ? undefined : Number(score), notes: notes || undefined }
    move.mutate({ id: t.id, body }, { onSuccess: () => setCompleting(false) })
  }

  return (
    <li className="rounded-lg border border-line bg-surface p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{t.key}</span>
        <span>{t.title}</span>
        <span className="text-xs uppercase text-ink-3">{t.priority}</span>
        <TaskStatusChip status={t.status} overdue={t.overdue} />
      </div>
      <p className="mt-1 text-sm text-ink-2">
        {who} · {t.due_at ? `due ${relative(t.due_at)}` : 'no due date'}
        {t.asset_id && <> · <Link className="text-moss hover:underline" to={`/w/${ws}/assets/${t.asset_id}`}>{t.asset_label}</Link></>}
        {t.issue_id && <> · <Link className="text-moss hover:underline" to={`/w/${ws}/issues/${t.issue_id}`}>{t.issue_key}</Link></>}
      </p>
      {canMove && !completing && (
        <div className="mt-2 flex flex-wrap gap-2">
          {(NEXT[t.status] ?? []).filter(() => !(reopening && !isManager)).map((n) => (
            <button key={n.to} type="button" className={n.to === 'done' ? btnPrimary : btn} disabled={move.isPending}
              onClick={() => (n.to === 'done' ? setCompleting(true) : move.mutate({ id: t.id, body: { to_status: n.to } }))}>
              {n.text}
            </button>
          ))}
          {!reopening && isManager && <button type="button" className={btn} disabled={move.isPending} onClick={() => move.mutate({ id: t.id, body: { to_status: 'cancelled' } })}>Cancel task</button>}
        </div>
      )}
      {completing && (
        <form onSubmit={complete} className="mt-2 space-y-2" aria-label={`Complete ${t.key}`}>
          <Field id={`n-${t.id}`} label="What was done?"><input id={`n-${t.id}`} name="note" className={input} maxLength={2000} /></Field>
          {t.asset_id && (
            <fieldset className="grid gap-2 rounded border border-line p-2 sm:grid-cols-2">
              <legend className="px-1 text-xs text-ink-3">Follow-up check (updates the asset's health)</legend>
              <Field id={`s-${t.id}`} label="Health score now (0–100)"><input id={`s-${t.id}`} name="score" type="number" min={0} max={100} step="any" className={input} /></Field>
              <Field id={`f-${t.id}`} label="What did you observe?"><input id={`f-${t.id}`} name="fnotes" className={input} /></Field>
            </fieldset>
          )}
          <div className="flex gap-2"><button className={btnPrimary} disabled={move.isPending}>Mark done</button><button type="button" className={btn} onClick={() => setCompleting(false)}>Cancel</button></div>
        </form>
      )}
      {move.error != null && <p role="alert" className="mt-2 text-sm text-critical">{errorMessage(move.error)}</p>}
    </li>
  )
}

export function TasksPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const { user } = useAuth()
  const [tab, setTab] = useState<'mine' | 'open' | 'done'>('mine')
  const [offset, setOffset] = useState(0)
  const params = tab === 'mine' ? { assignee: 'me', is_open: true } : tab === 'open' ? { is_open: true } : { is_open: false }
  const list = useTasks(ws, { ...params, limit: PAGE, offset })
  const isManager = atLeast(workspace.role, 'manager')
  const canWork = atLeast(workspace.role, 'worker')

  return (
    <div>
      <PageHeader title="Tasks" subtitle="Assigned work with due dates. Completing a task can record a follow-up check that updates the asset." />
      <div role="group" aria-label="Task scope" className="mb-3 inline-flex overflow-hidden rounded border border-line text-sm">
        {([['mine', 'My tasks'], ['open', 'All open'], ['done', 'Done / cancelled']] as const).map(([k, text]) => (
          <button key={k} type="button" aria-pressed={tab === k} onClick={() => { setTab(k); setOffset(0) }} className={`px-3 py-1.5 ${tab === k ? 'bg-surface-2 font-medium' : 'hover:bg-surface-2'}`}>{text}</button>
        ))}
      </div>
      {list.isLoading && <LoadingBlock label="Loading tasks" />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data?.total === 0 && <EmptyState title={tab === 'mine' ? 'Nothing assigned to you' : 'No tasks here'}>Managers create tasks from an issue, or accept an inspection suggestion from the Home page.</EmptyState>}
      <ul className="space-y-2">
        {list.data?.items.map((t) => (
          <Row key={`${t.id}-${t.version}`} t={t} ws={ws} isManager={isManager} canMove={isManager || (canWork && t.assignee_id === user?.id)} />
        ))}
      </ul>
      {list.data && <Pagination total={list.data.total} limit={PAGE} offset={offset} onChange={setOffset} />}
      <p className="sr-only">{label('tasks')}</p>
    </div>
  )
}
