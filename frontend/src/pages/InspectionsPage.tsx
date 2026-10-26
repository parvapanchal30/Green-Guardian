import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { InspectionSchedule, Page, Task } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { PageHeader, TaskStatusChip, btn } from '../components/domain'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { StatusChip } from '../components/StatusChip'
import { Icon } from '../components/icons'
import { LedgerTable, SectionHeading, Tag, type LedgerColumn } from '../components/ui'
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

  const columns: LedgerColumn<InspectionSchedule>[] = [
    { key: 'what', header: t('insp.what'), primary: true, cell: (s) => <span className="font-semibold">{s.title}</span> },
    {
      key: 'where', header: t('insp.where'),
      cell: (s) =>
        s.asset_id
          ? <Link className="text-moss hover:underline" to={`/w/${ws}/assets/${s.asset_id}`}>{s.asset_label}</Link>
          : <Link className="text-moss hover:underline" to={`/w/${ws}/locations`}>{s.location_name}</Link>,
    },
    { key: 'rhythm', header: t('insp.rhythm'), cell: (s) => <span className="inline-flex items-center gap-1 text-ink-2"><Icon name="recurring" size={14} />{t('schedule.every', { count: s.interval_days })}</span> },
    { key: 'next', header: t('insp.next'), cell: (s) => <span className="font-mono text-xs">{s.active ? fmt.date(s.next_due_at) : '—'}</span> },
    { key: 'who', header: t('insp.who'), cell: (s) => who(s.assignee_id) ?? <span className="text-ink-3">{t('issue.unassigned')}</span> },
    {
      key: 'state', header: t('insp.state'),
      cell: (s) => (
        <span className="inline-flex flex-wrap items-center gap-2">
          <StatusChip tone={s.active ? 'live' : 'neutral'}>{s.active ? t('schedule.active') : t('schedule.paused')}</StatusChip>
          {isManager && (
            <button type="button" className={`${btn} px-2 py-0.5 text-xs`} disabled={update.isPending} onClick={() => update.mutate({ id: s.id, active: !s.active })}>
              {s.active ? t('schedule.pause') : t('schedule.resume')}
            </button>
          )}
        </span>
      ),
    },
  ]

  return (
    <div className="space-y-8">
      <div>
        <PageHeader title={t('insp.title')} subtitle={t('insp.subtitle')}>
          {isManager && <button type="button" className={btn} disabled={generate.isPending} onClick={() => generate.mutate(undefined as never)}><Icon name="recurring" size={16} />{t('schedule.generate')}</button>}
        </PageHeader>
        {generate.data && <p role="status" className="text-sm text-ink-2">{t('schedule.generated', { count: generate.data.created })}</p>}
        {generate.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(generate.error)}</p>}
      </div>

      <section aria-labelledby="due">
        <SectionHeading id="due" title={t('insp.due')}>
          {checks.data && <span className="font-mono text-xs text-ink-2">{checks.data.items.length}</span>}
        </SectionHeading>
        {checks.isLoading && <LoadingBlock label={t('insp.loading')} />}
        {checks.error && <ErrorState error={checks.error} onRetry={() => checks.refetch()} />}
        {checks.data && checks.data.items.length === 0 && <EmptyState icon="inspections" title={t('insp.noneDue')}>{t('insp.noneDueBody')}</EmptyState>}
        <ul className="space-y-2">
          {checks.data?.items.map((task) => (
            <li key={task.id} className={`flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border bg-surface px-3.5 py-3 text-sm ${task.overdue ? 'border-critical/40' : 'border-line'}`}>
              <Tag tone={task.overdue ? 'critical' : 'neutral'}>{task.key}</Tag>
              <span className="min-w-0 flex-1 font-semibold">{task.title}</span>
              <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-2">
                {task.asset_id && <Link className="inline-flex items-center gap-1 text-moss hover:underline" to={`/w/${ws}/assets/${task.asset_id}`}><Icon name="assets" size={14} />{task.asset_label}</Link>}
                {who(task.assignee_id) && <span className="inline-flex items-center gap-1"><Icon name="members" size={14} />{who(task.assignee_id)}</span>}
                <span className={`inline-flex items-center gap-1 ${task.overdue ? 'font-semibold text-critical' : ''}`}><Icon name="time" size={14} />{task.due_at ? t('tasks.due', { when: fmt.relative(task.due_at) }) : t('tasks.noDue')}</span>
              </span>
              <span className="flex items-center gap-2">
                <TaskStatusChip status={task.status} overdue={task.overdue} />
                {task.source === 'schedule' && <StatusChip tone="neutral">{te('taskSource', 'schedule')}</StatusChip>}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-ink-3">{t('insp.completeHint')} <Link className="underline" to={`/w/${ws}/tasks`}>{t('issue.tasksPage')}</Link> {t('issue.page')}</p>
      </section>

      <section aria-labelledby="rec">
        <SectionHeading id="rec" title={t('schedule.panelTitle')} />
        {schedules.isLoading && <LoadingBlock label={t('schedule.loading')} />}
        {schedules.error && <ErrorState error={schedules.error} onRetry={() => schedules.refetch()} />}
        {schedules.data && schedules.data.length === 0 && <EmptyState icon="recurring" title={t('insp.noSchedules')}>{t('insp.noSchedulesBody')}</EmptyState>}
        {schedules.data && schedules.data.length > 0 && <LedgerTable caption={t('schedule.panelTitle')} columns={columns} rows={schedules.data} rowKey={(s) => s.id} />}
        {update.error != null && <p role="alert" className="mt-2 text-sm text-critical">{errorMessage(update.error)}</p>}
        <p className="mt-2 text-xs text-ink-3">{t('insp.setupHint')}</p>
      </section>
    </div>
  )
}
