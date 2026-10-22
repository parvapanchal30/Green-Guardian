import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import type { Task } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { Field, PageHeader, Pagination, TaskStatusChip, btn, btnPrimary, input } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { useI18n, type TKey } from '../i18n'
import { atLeast } from '../lib/format'
import { useMembers } from '../lib/queries'
import { useTasks, useTransitionTask } from '../lib/slice'
import { useAuth } from '../lib/auth'

const PAGE = 25
// Allowed moves per status, with the catalog key of the button text.
const NEXT: Record<string, { to: string; text: TKey }[]> = {
  todo: [{ to: 'in_progress', text: 'tasks.action.in_progress' }, { to: 'done', text: 'tasks.action.done' }],
  in_progress: [{ to: 'done', text: 'tasks.action.done' }, { to: 'blocked', text: 'tasks.action.blocked' }],
  blocked: [{ to: 'in_progress', text: 'tasks.action.resume' }],
  done: [{ to: 'in_progress', text: 'tasks.action.reopen' }],
  cancelled: [{ to: 'todo', text: 'tasks.action.reopen' }],
}

function Row({ t: task, ws, canMove, isManager }: { t: Task; ws: string; canMove: boolean; isManager: boolean }) {
  const { t, fmt } = useI18n()
  const move = useTransitionTask(ws)
  const [completing, setCompleting] = useState(false)
  const members = useMembers(ws)
  const who = members.data?.find((m) => m.user_id === task.assignee_id)?.name ?? (task.assignee_id ? t('tasks.assigned') : t('tasks.unassigned'))
  const reopening = task.status === 'done' || task.status === 'cancelled'

  function complete(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const score = String(f.get('score') ?? '').trim()
    const notes = String(f.get('fnotes') ?? '').trim()
    const body: Record<string, unknown> = { to_status: 'done', note: String(f.get('note') ?? '').trim() || undefined }
    if (task.asset_id && (score !== '' || notes)) body.observation = { health_score: score === '' ? undefined : Number(score), notes: notes || undefined }
    move.mutate({ id: task.id, body }, { onSuccess: () => setCompleting(false) })
  }

  return (
    <li className="rounded-lg border border-line bg-surface p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{task.key}</span>
        <span>{task.title}</span>
        <span className="text-xs uppercase text-ink-3">{task.priority}</span>
        <TaskStatusChip status={task.status} overdue={task.overdue} />
      </div>
      <p className="mt-1 text-sm text-ink-2">
        {who} · {task.due_at ? t('tasks.due', { when: fmt.relative(task.due_at) }) : t('tasks.noDue')}
        {task.asset_id && <> · <Link className="text-moss hover:underline" to={`/w/${ws}/assets/${task.asset_id}`}>{task.asset_label}</Link></>}
        {task.issue_id && <> · <Link className="text-moss hover:underline" to={`/w/${ws}/issues/${task.issue_id}`}>{task.issue_key}</Link></>}
      </p>
      {canMove && !completing && (
        <div className="mt-2 flex flex-wrap gap-2">
          {(NEXT[task.status] ?? []).filter(() => !(reopening && !isManager)).map((n) => (
            <button key={n.to} type="button" className={n.to === 'done' ? btnPrimary : btn} disabled={move.isPending}
              onClick={() => (n.to === 'done' ? setCompleting(true) : move.mutate({ id: task.id, body: { to_status: n.to } }))}>
              {t(n.text)}
            </button>
          ))}
          {!reopening && isManager && <button type="button" className={btn} disabled={move.isPending} onClick={() => move.mutate({ id: task.id, body: { to_status: 'cancelled' } })}>{t('tasks.cancelTask')}</button>}
        </div>
      )}
      {completing && (
        <form onSubmit={complete} className="mt-2 space-y-2" aria-label={t('tasks.completeForm', { key: task.key })}>
          <Field id={`n-${task.id}`} label={t('tasks.whatDone')}><input id={`n-${task.id}`} name="note" className={input} maxLength={2000} /></Field>
          {task.asset_id && (
            <fieldset className="grid gap-2 rounded border border-line p-2 sm:grid-cols-2">
              <legend className="px-1 text-xs text-ink-3">{t('tasks.followUp')}</legend>
              <Field id={`s-${task.id}`} label={t('tasks.scoreNow')}><input id={`s-${task.id}`} name="score" type="number" min={0} max={100} step="any" className={input} /></Field>
              <Field id={`f-${task.id}`} label={t('tasks.observed')}><input id={`f-${task.id}`} name="fnotes" className={input} /></Field>
            </fieldset>
          )}
          <div className="flex gap-2"><button className={btnPrimary} disabled={move.isPending}>{t('tasks.markDone')}</button><button type="button" className={btn} onClick={() => setCompleting(false)}>{t('tasks.cancel')}</button></div>
        </form>
      )}
      {move.error != null && <p role="alert" className="mt-2 text-sm text-critical">{errorMessage(move.error)}</p>}
    </li>
  )
}

const TABS = [['mine', 'tasks.tab.mine'], ['open', 'tasks.tab.open'], ['done', 'tasks.tab.done']] as const

export function TasksPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const { t } = useI18n()
  const { user } = useAuth()
  const [tab, setTab] = useState<'mine' | 'open' | 'done'>('mine')
  const [offset, setOffset] = useState(0)
  const params = tab === 'mine' ? { assignee: 'me', is_open: true } : tab === 'open' ? { is_open: true } : { is_open: false }
  const list = useTasks(ws, { ...params, limit: PAGE, offset })
  const isManager = atLeast(workspace.role, 'manager')
  const canWork = atLeast(workspace.role, 'worker')

  return (
    <div>
      <PageHeader title={t('tasks.title')} subtitle={t('tasks.subtitle')} />
      <div role="group" aria-label={t('tasks.scope')} className="mb-3 inline-flex overflow-hidden rounded border border-line text-sm">
        {TABS.map(([k, key]) => (
          <button key={k} type="button" aria-pressed={tab === k} onClick={() => { setTab(k); setOffset(0) }} className={`px-3 py-1.5 ${tab === k ? 'bg-surface-2 font-medium' : 'hover:bg-surface-2'}`}>{t(key)}</button>
        ))}
      </div>
      {list.isLoading && <LoadingBlock label={t('tasks.loading')} />}
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.data?.total === 0 && <EmptyState title={tab === 'mine' ? t('tasks.noneMine') : t('tasks.none')}>{t('tasks.emptyBody')}</EmptyState>}
      <ul className="space-y-2">
        {list.data?.items.map((task) => (
          <Row key={`${task.id}-${task.version}`} t={task} ws={ws} isManager={isManager} canMove={isManager || (canWork && task.assignee_id === user?.id)} />
        ))}
      </ul>
      {list.data && <Pagination total={list.data.total} limit={PAGE} offset={offset} onChange={setOffset} />}
    </div>
  )
}
