import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { EmptyState, ErrorState, LoadingBlock } from '../components/states'
import { useMembers } from '../lib/queries'

export function MembersPage() {
  const { ws, workspace } = useWorkspaceCtx()
  const q = useMembers(ws)
  const canManage = workspace.role === 'owner' || workspace.role === 'admin'
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Members</h1>
      <p className="text-ink-2">
        People with access to this workspace. {canManage ? 'You can manage members through the API; the invite interface is in development.' : 'Only owners and admins can change membership.'}
      </p>
      {q.isLoading && <LoadingBlock label="Loading members" />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data?.length === 0 && <EmptyState title="No members" />}
      {q.data && q.data.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Workspace members</caption>
            <thead className="border-b border-line text-ink-2">
              <tr><th className="p-2 font-medium">Name</th><th className="p-2 font-medium">Email</th><th className="p-2 font-medium">Role</th></tr>
            </thead>
            <tbody>
              {q.data.map((m) => (
                <tr key={m.user_id} className="border-b border-line last:border-0">
                  <td className="p-2">{m.name}</td><td className="p-2 text-ink-2">{m.email}</td><td className="p-2">{m.role}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
