import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { router } from './app/router'
import './styles/fonts'
import './index.css'
import { applyTheme, readTheme } from './lib/theme'

applyTheme(readTheme()) // before the first paint, so a chosen theme never flashes the other one

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router()} />
  </StrictMode>,
)
