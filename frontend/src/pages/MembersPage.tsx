import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { EmptyState, ErrorState, LoadingBlock } from '../components/states'
import { useMembers } from '../lib/queries'
import { useI18n } from '../i18n'

export function MembersPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const q = useMembers(ws)
  const { t, te } = useI18n()
  const canManage = workspace.role === 'owner' || workspace.role === 'admin'
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">{t('members.title')}</h1>
      <p className="text-ink-2">
        {t('members.intro')} {canManage ? t('members.canManage') : t('members.cannotManage')}
      </p>
      {q.isLoading && <LoadingBlock label={t('members.loading')} />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data?.length === 0 && <EmptyState title={t('members.none')} />}
      {q.data && q.data.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">{t('members.caption')}</caption>
            <thead className="border-b border-line text-ink-2">
              <tr><th className="p-2 font-medium">{t('members.name')}</th><th className="p-2 font-medium">{t('members.email')}</th><th className="p-2 font-medium">{t('members.role')}</th></tr>
            </thead>
            <tbody>
              {q.data.map((m) => (
                <tr key={m.user_id} className="border-b border-line last:border-0">
                  <td className="p-2">{m.name}</td><td className="p-2 text-ink-2">{m.email}</td><td className="p-2">{te('role', m.role)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
