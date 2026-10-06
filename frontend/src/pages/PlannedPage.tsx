import { useLocation } from 'react-router-dom'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { ROUTES } from '../app/routes'
import { CapabilityGate, ComingSoonPanel } from '../components/CapabilityGate'
import { PREVIEWS } from '../components/previews'
import { VOCABULARY } from '../lib/vocabulary'

/**
 * One page component serves every route that is not live yet. It never shows data:
 *  - status "building": MVP surface not built yet ("In development")
 *  - status "soon": future surface behind a backend capability ("Coming soon"), with a disabled real layout
 */
export function PlannedPage({ routePath }: { routePath: string }) {
  const { ws, workspace, capabilities } = useWorkspaceCtx()
  const { pathname } = useLocation()
  const route = ROUTES.find((r) => r.path === routePath)
  const vocab = VOCABULARY[workspace.mode]
  if (!route) return null
  const Preview = route.capability ? PREVIEWS[route.capability] : undefined

  const body = route.capability ? (
    <CapabilityGate
      feature={route.capability}
      capabilities={capabilities}
      title={route.label}
      summary={route.summary}
      preview={Preview ? <Preview /> : undefined}
    >
      {/* The capability is enabled server-side but this interface has not been built yet. */}
      <ComingSoonPanel title={route.label} summary={route.summary} stage="mvp" reason="Capability is enabled; its interface is not built yet" />
    </CapabilityGate>
  ) : (
    <ComingSoonPanel
      title={route.label.replace('Zones', vocab.locations)}
      summary={route.summary}
      stage="mvp"
      reason="Part of the MVP; backend and interface are still being built"
    />
  )

  return (
    <div className="space-y-4" data-route={pathname.replace(`/w/${ws}`, '') || '/'}>
      {body}
    </div>
  )
}
