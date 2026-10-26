import { Link, Navigate, createBrowserRouter, type RouteObject } from 'react-router-dom'
import { useI18n } from '../i18n'
import { AuthProvider } from '../lib/auth'
import { AgentPage } from '../pages/AgentPage'
import { AssetProfilePage } from '../pages/AssetProfilePage'
import { AuditPage } from '../pages/AuditPage'
import { DatasetDetailPage } from '../pages/DatasetDetailPage'
import { DatasetsPage } from '../pages/DatasetsPage'
import { ProtocolDetailPage, ProtocolsPage } from '../pages/ProtocolsPage'
import { AssetsPage } from '../pages/AssetsPage'
import { HomePage } from '../pages/HomePage'
import { IssueDetailPage } from '../pages/IssueDetailPage'
import { IssuesPage } from '../pages/IssuesPage'
import { TasksPage } from '../pages/TasksPage'
import { LoginPage, RegisterPage } from '../pages/AuthPages'
import { MapPage } from '../pages/MapPage'
import { MembersPage } from '../pages/MembersPage'
import { PlannedPage } from '../pages/PlannedPage'
import { SpeciesPage } from '../pages/SpeciesPage'
import { LocationsPage } from '../pages/LocationsPage'
import { InspectionsPage } from '../pages/InspectionsPage'
import { HarvestsPage } from '../pages/HarvestsPage'
import { HealthPage } from '../pages/HealthPage'
import { GrowthPage } from '../pages/GrowthPage'
import { AnalyticsPage, ImpactPage } from '../pages/ReportsPages'
import { WeatherPage } from '../pages/WeatherPage'
import { ComingNextPage } from '../pages/ComingNextPage'
import { WorkspacesPage } from '../pages/WorkspacesPage'
import { ROUTES } from './routes'
import { RequireAuth, WorkspaceLayout } from './WorkspaceLayout'
import { Providers } from './providers'
import { Outlet } from 'react-router-dom'

function Root() {
  return (
    <Providers>
      <AuthProvider>
        <Outlet />
      </AuthProvider>
    </Providers>
  )
}

function NotFound() {
  const { t } = useI18n()
  return (
    <div className="grid min-h-screen place-items-center p-4 text-center">
      <div>
        <h1 className="text-xl font-semibold">{t('common.notFound')}</h1>
        <Link to="/" className="text-moss underline">{t('common.goToWorkspaces')}</Link>
      </div>
    </div>
  )
}

const LIVE: Record<string, () => React.JSX.Element> = {
  '': HomePage,
  assets: AssetsPage,
  'assets/trees': () => <AssetsPage only="tree" />,
  'assets/plants': () => <AssetsPage only="plant" />,
  'assets/batches': () => <AssetsPage only="crop_batch" />,
  'assets/species': () => <SpeciesPage />,
  'assets/crops': () => <SpeciesPage crops />,
  locations: LocationsPage,
  inspections: InspectionsPage,
  harvests: HarvestsPage,
  'monitor/health': HealthPage,
  'monitor/growth': GrowthPage,
  'reports/analytics': AnalyticsPage,
  'reports/impact': ImpactPage,
  tasks: TasksPage,
  issues: IssuesPage,
  'ai/agent': AgentPage,
  'ai/datasets': DatasetsPage,
  'ai/protocols': ProtocolsPage,
  'monitor/map': MapPage,
  'monitor/weather': WeatherPage,
  'settings/members': MembersPage,
  'settings/audit': AuditPage,
  'coming-next': ComingNextPage,
}

// Detail pages are reachable by link, not from the sidebar.
const detailRoutes: RouteObject[] = [
  { path: 'assets/:assetId', element: <AssetProfilePage /> },
  { path: 'issues/:issueId', element: <IssueDetailPage /> },
  { path: 'ai/datasets/:datasetId', element: <DatasetDetailPage /> },
  { path: 'ai/protocols/:protocolId', element: <ProtocolDetailPage /> },
]

const workspaceChildren: RouteObject[] = ROUTES.map((r) => {
  const Live = LIVE[r.path]
  const element = Live ? <Live /> : <PlannedPage routePath={r.path} />
  return r.path === '' ? { index: true, element } : { path: r.path, element }
})

export const routes: RouteObject[] = [
  {
    element: <Root />,
    children: [
      { path: '/login', element: <LoginPage /> },
      { path: '/register', element: <RegisterPage /> },
      { path: '/', element: <RequireAuth><WorkspacesPage /></RequireAuth> },
      { path: '/w/:ws', element: <RequireAuth><WorkspaceLayout /></RequireAuth>, children: [...workspaceChildren, ...detailRoutes, { path: '*', element: <Navigate to="." replace /> }] },
      { path: '*', element: <NotFound /> },
    ],
  },
]

export const router = () => createBrowserRouter(routes)
