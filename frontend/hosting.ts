/**
 * Hosting rules for the production build (used by vite.config.ts and unit-tested in src/test/hosting.test.ts).
 *
 * The SPA is a static site on Vercel and the API lives on its own origin (see docs/HOSTING.md), so the browser calls the API
 * directly. Two things follow and are enforced here at BUILD time, because a wrong value would otherwise ship silently:
 *  1. VITE_API_BASE_URL must be an absolute https URL that is not localhost. Without it the app would call `/api/v1` on the
 *     static host, which has no API.
 *  2. The Content-Security-Policy must allow that one API origin in `connect-src` and nothing broader.
 *
 * Everything here is PUBLIC: Vite inlines `VITE_*` variables into the browser bundle. Never put a secret in one.
 */

export interface HostingEnv {
  /** True for any Vercel build (Vercel sets VERCEL=1). */
  onVercel: boolean
  /** Vercel's environment name: production, preview or development. */
  vercelEnv?: string
  apiBase?: string
  tileUrl?: string
}

const LOOPBACK = /^(localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|\[::1\]|::1)$/i
/** Reserved names that can never resolve to a real API (RFC 2606 `.invalid`, `.localhost`, mDNS `.local`): placeholders only. */
const RESERVED = /\.(invalid|localhost|local)$/i
const DEFAULT_TILE_HOSTS = ['https://tile.openstreetmap.org', 'https://*.tile.openstreetmap.org']

function parseAbsolute(url: string | undefined): URL | null {
  if (!url) return null
  try {
    return new URL(url)
  } catch {
    return null
  }
}

/** Problems that must stop a hosted build. Empty means the configuration is acceptable. */
export function hostingProblems(env: HostingEnv): string[] {
  if (!env.onVercel) return []
  const problems: string[] = []
  const api = parseAbsolute(env.apiBase)
  if (!env.apiBase) {
    problems.push('VITE_API_BASE_URL is not set: set it to the public https URL of the API, for example https://api.example.org/api/v1 (a public value, never a secret)')
  } else if (!api) {
    problems.push('VITE_API_BASE_URL must be an absolute URL (it is not a valid URL)')
  } else {
    if (api.protocol !== 'https:') problems.push('VITE_API_BASE_URL must use https')
    if (LOOPBACK.test(api.hostname)) problems.push('VITE_API_BASE_URL points at a local address, which would not work for visitors')
    if (RESERVED.test(api.hostname)) problems.push('VITE_API_BASE_URL uses a reserved placeholder host (.invalid, .localhost or .local) that can never be a working API: set the real staging or production API URL')
    if (api.username || api.password) problems.push('VITE_API_BASE_URL must not contain credentials')
  }
  if (env.tileUrl) {
    const tiles = parseAbsolute(env.tileUrl.replace('{s}', 'a').replace('{z}', '0').replace('{x}', '0').replace('{y}', '0'))
    if (!tiles || tiles.protocol !== 'https:') problems.push('VITE_MAP_TILE_URL must be an https URL template')
  }
  return problems
}

/** Origin the browser may connect to besides the page itself, or null if the API is same-origin. */
export function apiOrigin(apiBase: string | undefined): string | null {
  const u = parseAbsolute(apiBase)
  return u ? u.origin : null
}

function tileHosts(tileUrl: string | undefined): string[] {
  if (!tileUrl) return DEFAULT_TILE_HOSTS
  const u = parseAbsolute(tileUrl.replace('{s}', 'wildcard-subdomain'))
  if (!u) return DEFAULT_TILE_HOSTS
  const host = u.hostname.replace('wildcard-subdomain', '*')
  return [`${u.protocol}//${host}${u.port ? `:${u.port}` : ''}`]
}

/**
 * Content-Security-Policy for the hosted build, delivered as a <meta> tag (a build can read environment variables; a static
 * header file cannot). `frame-ancestors` is not honoured in a meta tag, so clickjacking protection is the X-Frame-Options
 * header in vercel.json.
 */
export function contentSecurityPolicy(env: Pick<HostingEnv, 'apiBase' | 'tileUrl'>): string {
  const api = apiOrigin(env.apiBase)
  const directives = [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'", // the map library sets inline styles
    `img-src 'self' data: blob: ${tileHosts(env.tileUrl).join(' ')}`,
    `connect-src 'self'${api ? ` ${api}` : ''}`,
    "font-src 'self' data:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ]
  return directives.join('; ')
}

/** Vite plugin: fail a hosted build with a bad configuration, and add the CSP to index.html of production builds. */
export function hostingPlugin(env: HostingEnv) {
  return {
    name: 'greenguardian-hosting',
    apply: 'build' as const,
    buildStart() {
      const problems = hostingProblems(env)
      if (problems.length) throw new Error(`Hosting configuration is not safe to build:\n - ${problems.join('\n - ')}`)
    },
    transformIndexHtml(html: string) {
      const csp = contentSecurityPolicy(env).replace(/"/g, '&quot;')
      return html.replace('<head>', `<head>\n    <meta http-equiv="Content-Security-Policy" content="${csp}" />`)
    },
  }
}
