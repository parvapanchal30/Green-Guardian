import { useState, type FormEvent } from 'react'
import type { Member, Role } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { PageHeader, btn, btnPrimary } from '../components/domain'
import { Icon } from '../components/icons'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { Card, LedgerTable, SectionHeading, Tag, type LedgerColumn } from '../components/ui'
import { useI18n, type TKey } from '../i18n'
import { atLeast } from '../lib/format'
import { useAuth } from '../lib/auth'
import { useMemberChanges, useMembers } from '../lib/queries'

const ROLES: Role[] = ['owner', 'admin', 'manager', 'worker', 'viewer']
const AVATAR = ['bg-soil', 'bg-info', 'bg-moss', 'bg-at-risk', 'bg-ink-2']

function initials(name: string) {
  return name.split(/[\s(]+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join('')
}

/**
 * Members (ADR-074). Owners and admins add people by the email they registered with, change roles and remove
 * members; the server keeps the rules (only owners touch the owner role, a workspace keeps one owner, nobody acts on
 * a higher role) and writes every change to the audit log.
 */
export function MembersPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const { user } = useAuth()
  const q = useMembers(ws)
  const { t, te } = useI18n()
  const change = useMemberChanges(ws)
  const canManage = atLeast(workspace.role, 'admin')
  const [adding, setAdding] = useState(false)
  const [removing, setRemoving] = useState<string | null>(null)
  // Roles this person may give: owners any, admins up to admin (the server checks again).
  const grantable = ROLES.filter((r) => (r === 'owner' ? workspace.role === 'owner' : atLeast(workspace.role, r)))
  const mayEdit = (m: Member) => canManage && m.user_id !== user?.id && (m.role !== 'owner' || workspace.role === 'owner') && atLeast(workspace.role, m.role)
  const failed = change.add.error ?? change.changeRole.error ?? change.remove.error

  function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    change.add.mutate({ email: String(f.get('email') ?? '').trim(), role: String(f.get('role')) as Role }, { onSuccess: () => setAdding(false) })
  }

  const columns: LedgerColumn<Member>[] = [
    {
      key: 'person', header: t('members.name'), primary: true,
      cell: (m) => (
        <span className="flex items-center gap-3">
          <span aria-hidden="true" className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold text-white ${AVATAR[m.name.length % AVATAR.length]}`}>{initials(m.name)}</span>
          <span className="flex min-w-0 flex-col">
            <b>{m.name}</b>
            <span className="truncate text-[13px] text-ink-2">{m.email}{m.user_id === user?.id && ` · ${t('members.you')}`}</span>
          </span>
        </span>
      ),
    },
    {
      key: 'role', header: t('members.role'),
      cell: (m) =>
        mayEdit(m) ? (
          <select
            aria-label={t('members.roleFor', { name: m.name })}
            value={m.role}
            disabled={change.changeRole.isPending}
            onChange={(e) => change.changeRole.mutate({ userId: m.user_id, role: e.target.value as Role })}
            className="rounded-md border border-line bg-surface px-2 py-1 text-sm"
          >
            {grantable.concat(grantable.includes(m.role) ? [] : [m.role]).map((r) => <option key={r} value={r}>{te('role', r)}</option>)}
          </select>
        ) : (
          <Tag tone={m.role === 'owner' ? 'moss' : 'neutral'}>{te('role', m.role)}</Tag>
        ),
    },
    {
      key: 'remove', header: t('members.access'),
      cell: (m) =>
        !mayEdit(m) ? <span className="text-ink-3">—</span> : removing === m.user_id ? (
          <span className="flex flex-wrap gap-2">
            <button type="button" className={`${btn} border-critical/50 px-2 py-1 text-xs text-critical`} disabled={change.remove.isPending} onClick={() => change.remove.mutate(m.user_id, { onSuccess: () => setRemoving(null) })}>
              {t('members.confirmRemove', { name: m.name })}
            </button>
            <button type="button" className={`${btn} px-2 py-1 text-xs`} onClick={() => setRemoving(null)}>{t('issue.cancel')}</button>
          </span>
        ) : (
          <button type="button" className={`${btn} px-2 py-1 text-xs`} onClick={() => setRemoving(m.user_id)}>{t('members.remove')}</button>
        ),
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <PageHeader eyebrow={t('eyebrow.settings')} title={t('members.title')} subtitle={t('members.subtitle', { name: workspace.name })}>
        {canManage && !adding && (
          <button type="button" className={btnPrimary} onClick={() => setAdding(true)}>
            <Icon name="add" size={16} />
            {t('members.add')}
          </button>
        )}
      </PageHeader>
      {!canManage && <p className="text-sm text-ink-2">{t('members.cannotManage')}</p>}
      {adding && (
        <form onSubmit={add} aria-label={t('members.add')} className="grid gap-3 rounded-lg border border-line bg-surface p-4 sm:grid-cols-[minmax(0,1fr)_12rem_auto] sm:items-end">
          <div>
            <label htmlFor="m-email" className="mb-1 block text-sm font-semibold">{t('members.email')}</label>
            <input id="m-email" name="email" type="email" required className="w-full rounded-md border border-line bg-surface px-2.5 py-1.5" />
            <p className="mt-1 text-xs text-ink-2">{t('members.addHint')}</p>
          </div>
          <div>
            <label htmlFor="m-role" className="mb-1 block text-sm font-semibold">{t('members.role')}</label>
            <select id="m-role" name="role" defaultValue="worker" className="w-full rounded-md border border-line bg-surface px-2.5 py-1.5">
              {grantable.map((r) => <option key={r} value={r}>{te('role', r)}</option>)}
            </select>
          </div>
          <div className="flex gap-2 sm:mb-5">
            <button className={btnPrimary} disabled={change.add.isPending}>{t('members.addButton')}</button>
            <button type="button" className={btn} onClick={() => setAdding(false)}>{t('issue.cancel')}</button>
          </div>
        </form>
      )}
      {failed != null && <p role="alert" className="text-sm text-critical">{errorMessage(failed)}</p>}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div>
          {q.isLoading && <LoadingBlock label={t('members.loading')} />}
          {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
          {q.data?.length === 0 && <EmptyState icon="members" title={t('members.none')} />}
          {q.data && q.data.length > 0 && <LedgerTable caption={t('members.caption')} columns={canManage ? columns : columns.slice(0, 2)} rows={q.data} rowKey={(m) => m.user_id} />}
        </div>
        <Card className="px-4 py-3.5">
          <section aria-labelledby="roles">
            <SectionHeading id="roles" title={t('members.rolesTitle')} />
            <dl>
              {ROLES.map((r) => (
                <div key={r} className="grid grid-cols-[84px_minmax(0,1fr)] gap-2.5 border-b border-line-soft py-2.5 text-[13.5px] last:border-0">
                  <dt className="font-semibold">{te('role', r)}</dt>
                  <dd className="text-ink-2">{t(`members.can.${r}` as TKey)}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-2 text-xs text-ink-2">{t('members.audited')}</p>
          </section>
        </Card>
      </div>
    </div>
  )
}
