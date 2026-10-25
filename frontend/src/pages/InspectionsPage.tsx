import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Page, Task } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { PageHeader, TaskStatusChip, btn } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { StatusChip } from '../components/StatusChip'
import { useI18n } from '../i18n'
import { atLeast } from '../lib/format'
import { useMembers } from '../lib/queries'
import { useGenerateDue, useSchedules, useUpdateSchedule } from '../lib/schedules'

/** Open inspection and monitoring tasks, nearest due date first (the list endpoint takes the type more than once). */
const useOpenChecks = (ws: string) =>
  useQuery({
    queryKey: [ws, 'tasks', 'checks'],
    queryFn: () => api<Page<Task>>(`/workspaces/${ws}/tasks?type=inspect&type=monitor&is_open=true&limit=100`),
  })

/**
 * Inspections: what has to be looked at (open inspection and monitoring tasks, whether a person, a rule or a schedule
 * created them) and the recurring schedules that keep creating them.
 */
export function InspectionsPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const { t, te, fmt } = useI18n()
  const checks = useOpenChecks(ws)
  const schedules = useSchedules(ws)
  const generate = useGenerateDue(ws)
  const update = useUpdateSchedule(ws)
  const members = useMembers(ws)
  const isManager = atLeast(workspace.role, 'manager')
  const who = (id: string | null) => members.data?.find((m) => m.user_id === id)?.name

  return (
    <div className="space-y-6">
      <PageHeader title={t('insp.title')} subtitle={t('insp.subtitle')}>
        {isManager && <button type="button" className={btn} disabled={generate.isPending} onClick={() => generate.mutate(undefined as never)}>{t('schedule.generate')}</button>}
      </PageHeader>
      {generate.data && <p role="status" className="text-sm text-ink-2">{t('schedule.generated', { count: generate.data.created })}</p>}
      {generate.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(generate.error)}</p>}

      <section aria-labelledby="due">
        <h2 id="due" className="mb-2 font-semibold">{t('insp.due')}</h2>
        {checks.isLoading && <LoadingBlock label={t('insp.loading')} />}
        {checks.error && <ErrorState error={checks.error} onRetry={() => checks.refetch()} />}
        {checks.data && checks.data.items.length === 0 && <EmptyState title={t('insp.noneDue')}>{t('insp.noneDueBody')}</EmptyState>}
        <ul className="space-y-2">
          {checks.data?.items.map((task) => (
            <li key={task.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface p-3 text-sm">
              <span className="font-medium">{task.key}</span>
              <span>{task.title}</span>
              <TaskStatusChip status={task.status} overdue={task.overdue} />
              {task.source === 'schedule' && <StatusChip tone="neutral">{te('taskSource', 'schedule')}</StatusChip>}
              <span className="text-ink-2">{task.due_at ? t('tasks.due', { when: fmt.relative(task.due_at) }) : t('tasks.noDue')}</span>
              {task.asset_id && <Link className="text-moss hover:underline" to={`/w/${ws}/assets/${task.asset_id}`}>{task.asset_label}</Link>}
              {who(task.assignee_id) && <span className="text-ink-3">{who(task.assignee_id)}</span>}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-ink-3">{t('insp.completeHint')} <Link className="underline" to={`/w/${ws}/tasks`}>{t('issue.tasksPage')}</Link> {t('issue.page')}</p>
      </section>

      <section aria-labelledby="rec">
        <h2 id="rec" className="mb-2 font-semibold">{t('schedule.panelTitle')}</h2>
        {schedules.isLoading && <LoadingBlock label={t('schedule.loading')} />}
        {schedules.error && <ErrorState error={schedules.error} onRetry={() => schedules.refetch()} />}
        {schedules.data && schedules.data.length === 0 && <EmptyState title={t('insp.noSchedules')}>{t('insp.noSchedulesBody')}</EmptyState>}
        {schedules.data && schedules.data.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">{t('schedule.panelTitle')}</caption>
              <thead className="border-b border-line text-ink-2">
                <tr>
                  <th className="p-2 font-medium">{t('insp.what')}</th>
                  <th className="p-2 font-medium">{t('insp.where')}</th>
                  <th className="p-2 font-medium">{t('insp.rhythm')}</th>
                  <th className="p-2 font-medium">{t('insp.next')}</th>
                  <th className="p-2 font-medium">{t('insp.who')}</th>
                  <th className="p-2 font-medium">{t('insp.state')}</th>
                </tr>
              </thead>
              <tbody>
                {schedules.data.map((s) => (
                  <tr key={s.id} className="border-b border-line last:border-0">
                    <td className="p-2">{s.title}</td>
                    <td className="p-2">
                      {s.asset_id ? <Link className="text-moss hover:underline" to={`/w/${ws}/assets/${s.asset_id}`}>{s.asset_label}</Link> : <Link className="text-moss hover:underline" to={`/w/${ws}/locations`}>{s.location_name}</Link>}
                    </td>
                    <td className="p-2">{t('schedule.every', { count: s.interval_days })}</td>
                    <td className="p-2">{s.active ? fmt.date(s.next_due_at) : '—'}</td>
                    <td className="p-2">{who(s.assignee_id) ?? <span className="text-ink-3">{t('issue.unassigned')}</span>}</td>
                    <td className="p-2">
                      <StatusChip tone={s.active ? 'live' : 'neutral'}>{s.active ? t('schedule.active') : t('schedule.paused')}</StatusChip>
                      {isManager && (
                        <button type="button" className={`${btn} ml-2 px-2 py-0.5 text-xs`} disabled={update.isPending} onClick={() => update.mutate({ id: s.id, active: !s.active })}>
                          {s.active ? t('schedule.pause') : t('schedule.resume')}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {update.error != null && <p role="alert" className="mt-2 text-sm text-critical">{errorMessage(update.error)}</p>}
        <p className="mt-2 text-xs text-ink-3">{t('insp.setupHint')}</p>
      </section>
    </div>
  )
}
