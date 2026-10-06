import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { StatusChip } from '../components/StatusChip'
import { EmptyState, LoadingBlock } from '../components/states'
import { VOCABULARY } from '../lib/vocabulary'

export function HomePage() {
  const { workspace, capabilities } = useWorkspaceCtx()
  const v = VOCABULARY[workspace.mode]

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{workspace.name}</h1>
        <p className="text-ink-2">{v.modeLabel} · {v.audience}</p>
      </header>

      <section aria-labelledby="kpis">
        <h2 id="kpis" className="mb-1 text-lg font-semibold">{v.kpis.join(' → ')}</h2>
        <p className="mb-3 text-sm text-ink-2">Every figure here will be computed from recorded observations. Until assets and observations exist, nothing is estimated or shown.</p>
        <ul className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {v.kpis.map((k) => (
            <li key={k} className="rounded-lg border border-line bg-surface p-3">
              <p className="text-sm text-ink-2">{k}</p>
              <p className="mt-1 text-sm font-medium text-ink-3">No data yet</p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="attention">
        <h2 id="attention" className="mb-3 text-lg font-semibold">Needs attention</h2>
        <EmptyState title="Nothing to review">
          The Botanical Operations Agent will list recommendations here, each with the rule that produced it. It is still in development, so no recommendations are generated yet.
        </EmptyState>
      </section>

      <section aria-labelledby="caps">
        <h2 id="caps" className="mb-3 text-lg font-semibold">What is live in this workspace</h2>
        {!capabilities ? (
          <LoadingBlock label="Loading capabilities" />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Capabilities and their availability</caption>
              <thead className="border-b border-line text-ink-2">
                <tr><th className="p-2 font-medium">Capability</th><th className="p-2 font-medium">Technique</th><th className="p-2 font-medium">Status</th></tr>
              </thead>
              <tbody>
                {capabilities.map((c) => (
                  <tr key={c.key} className="border-b border-line last:border-0">
                    <td className="p-2">{c.label}</td>
                    <td className="p-2 text-ink-2">{c.technique}</td>
                    <td className="p-2">
                      {c.available ? <StatusChip tone="live">Live</StatusChip> : <StatusChip tone={c.stage === 'mvp' ? 'building' : 'soon'}>{c.stage === 'mvp' ? 'In development' : `Planned · ${c.stage.toUpperCase()}`}</StatusChip>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
