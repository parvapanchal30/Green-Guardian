import { Link, Navigate, createBrowserRouter, type RouteObject } from 'react-router-dom'
import { AuthProvider } from '../lib/auth'
import { AgentPage } from '../pages/AgentPage'
import { AssetProfilePage } from '../pages/AssetProfilePage'
import { AssetsPage } from '../pages/AssetsPage'
import { HomePage } from '../pages/HomePage'
import { IssueDetailPage } from '../pages/IssueDetailPage'
import { IssuesPage } from '../pages/IssuesPage'
import { TasksPage } from '../pages/TasksPage'
import { LoginPage, RegisterPage } from '../pages/AuthPages'
import { MapPage } from '../pages/MapPage'
import { MembersPage } from '../pages/MembersPage'
import { PlannedPage } from '../pages/PlannedPage'
import { WeatherPage } from '../pages/WeatherPage'
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
  return (
    <div className="grid min-h-screen place-items-center p-4 text-center">
      <div>
        <h1 className="text-xl font-semibold">Page not found</h1>
        <Link to="/" className="text-moss underline">Go to your workspaces</Link>
      </div>
    </div>
  )
}

const LIVE: Record<string, () => React.JSX.Element> = {
  '': HomePage,
  assets: AssetsPage,
  tasks: TasksPage,
  issues: IssuesPage,
  'ai/agent': AgentPage,
  'monitor/map': MapPage,
  'monitor/weather': WeatherPage,
  'settings/members': MembersPage,
}

// Detail pages are reachable by link, not from the sidebar.
const detailRoutes: RouteObject[] = [
  { path: 'assets/:assetId', element: <AssetProfilePage /> },
  { path: 'issues/:issueId', element: <IssueDetailPage /> },
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
