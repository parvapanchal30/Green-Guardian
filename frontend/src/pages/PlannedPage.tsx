import { useLocation } from 'react-router-dom'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { ROUTES, routeKey, routeSummaryKey } from '../app/routes'
import { CapabilityGate, ComingSoonPanel } from '../components/CapabilityGate'
import { PREVIEWS } from '../components/previews'
import { useI18n } from '../i18n'

/**
 * One page component serves every route that is not live yet. It never shows data:
 *  - status "building": MVP surface not built yet ("In development")
 *  - status "soon": future surface behind a backend capability ("Coming soon"), with a disabled real layout
 */
export function PlannedPage({ routePath }: { routePath: string }) {
  const { ws, capabilities } = useWorkspaceCtx()
  const { t } = useI18n()
  const { pathname } = useLocation()
  const route = ROUTES.find((r) => r.path === routePath)
  if (!route) return null
  const Preview = route.capability ? PREVIEWS[route.capability] : undefined
  const title = t(routeKey(route))
  const summary = route.summary ? t(routeSummaryKey(route)) : undefined

  const body = route.capability ? (
    <CapabilityGate
      feature={route.capability}
      capabilities={capabilities}
      title={title}
      summary={summary}
      preview={Preview ? <Preview /> : undefined}
    >
      {/* The capability is enabled server-side but this interface has not been built yet. */}
      <ComingSoonPanel title={title} summary={summary} stage="mvp" reason={t('soon.reason.enabledNotBuilt')} />
    </CapabilityGate>
  ) : (
    <ComingSoonPanel title={title} summary={summary} stage="mvp" reason={t('soon.reason.mvpBuilding')} />
  )

  return (
    <div className="space-y-4" data-route={pathname.replace(`/w/${ws}`, '') || '/'}>
      {body}
    </div>
  )
}
