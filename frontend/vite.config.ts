import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'
import { hostingPlugin } from './hosting.ts'

// Dev: the SPA talks to the FastAPI backend through a same-origin proxy (no CORS needed locally).
// Build: `hostingPlugin` refuses a hosted (Vercel) build whose API URL is missing, local or not https, and adds a
// Content-Security-Policy that allows exactly that one API origin. See docs/HOSTING.md.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  return {
    plugins: [
      react(),
      tailwindcss(),
      hostingPlugin({
        onVercel: Boolean(process.env.VERCEL),
        vercelEnv: process.env.VERCEL_ENV,
        apiBase: env.VITE_API_BASE_URL,
        tileUrl: env.VITE_MAP_TILE_URL,
      }),
    ],
    server: {
      port: 5173,
      proxy: { '/api': { target: process.env.VITE_DEV_API_TARGET ?? 'http://localhost:8000', changeOrigin: true } },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      css: false,
    },
  }
})
