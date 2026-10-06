import { Link, Navigate, createBrowserRouter, type RouteObject } from 'react-router-dom'
import { AuthProvider } from '../lib/auth'
import { HomePage } from '../pages/HomePage'
import { LoginPage, RegisterPage } from '../pages/AuthPages'
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
  'monitor/weather': WeatherPage,
  'settings/members': MembersPage,
}

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
      { path: '/w/:ws', element: <RequireAuth><WorkspaceLayout /></RequireAuth>, children: [...workspaceChildren, { path: '*', element: <Navigate to="." replace /> }] },
      { path: '*', element: <NotFound /> },
    ],
  },
]

export const router = () => createBrowserRouter(routes)
