import { spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { apiOrigin, contentSecurityPolicy, hostingPlugin, hostingProblems } from '../../hosting'

const API = 'https://api.greenguardian.example/api/v1'

describe('hosting configuration guard', () => {
  it('does nothing outside a hosted build (local, Docker and CI builds keep the same-origin default)', () => {
    expect(hostingProblems({ onVercel: false })).toEqual([])
    expect(hostingProblems({ onVercel: false, apiBase: 'http://localhost:8000/api/v1' })).toEqual([])
  })

  it('refuses a hosted build without an API URL', () => {
    const [p] = hostingProblems({ onVercel: true })
    expect(p).toMatch(/VITE_API_BASE_URL is not set/)
    expect(p).toMatch(/never a secret/)
  })

  it.each([
    ['http://api.example.org/api/v1', /must use https/],
    ['https://localhost/api/v1', /local address/],
    ['https://127.0.0.1:8000/api/v1', /local address/],
    ['https://0.0.0.0/api/v1', /local address/],
    ['https://[::1]/api/v1', /local address/],
    ['https://api.greenguardian-preview.invalid/api/v1', /reserved placeholder host/],
    ['https://api.team.localhost/api/v1', /reserved placeholder host/],
    ['/api/v1', /absolute URL/],
    ['not a url', /absolute URL/],
    ['https://user:pw@api.example.org/api/v1', /credentials/],
  ])('refuses the API URL %s', (apiBase, message) => {
    expect(hostingProblems({ onVercel: true, apiBase }).join('|')).toMatch(message)
  })

  it('accepts a public https API URL, and checks the tile template too', () => {
    expect(hostingProblems({ onVercel: true, apiBase: API })).toEqual([])
    expect(hostingProblems({ onVercel: true, apiBase: API, tileUrl: 'http://tiles.example/{z}/{x}/{y}.png' }).join()).toMatch(/VITE_MAP_TILE_URL/)
    expect(hostingProblems({ onVercel: true, apiBase: API, tileUrl: 'https://{s}.tiles.example/{z}/{x}/{y}.png' })).toEqual([])
  })

  it('the build plugin throws on a bad hosted configuration and passes a good one', () => {
    expect(() => hostingPlugin({ onVercel: true }).buildStart()).toThrow(/not safe to build/)
    expect(() => hostingPlugin({ onVercel: true, apiBase: API }).buildStart()).not.toThrow()
  })
})

describe('content security policy', () => {
  it('allows exactly the page and the one API origin to be connected to', () => {
    const csp = contentSecurityPolicy({ apiBase: API })
    expect(csp).toContain("connect-src 'self' https://api.greenguardian.example;")
    expect(csp).toContain("script-src 'self';")
    expect(csp).not.toMatch(/'unsafe-eval'|script-src[^;]*'unsafe-inline'/)
    expect(csp).toContain("object-src 'none'")
    expect(csp).not.toMatch(/connect-src[^;]*(\*|https: |http:)/)
  })

  it('a same-origin API adds nothing to connect-src', () => {
    expect(contentSecurityPolicy({ apiBase: '/api/v1' })).toContain("connect-src 'self';")
    expect(apiOrigin('/api/v1')).toBeNull()
    expect(apiOrigin(API)).toBe('https://api.greenguardian.example')
  })

  it('allows the configured tile host (with a wildcard subdomain for {s}) instead of the default', () => {
    expect(contentSecurityPolicy({ apiBase: API })).toContain('https://tile.openstreetmap.org https://*.tile.openstreetmap.org')
    const custom = contentSecurityPolicy({ apiBase: API, tileUrl: 'https://{s}.tiles.example/{z}/{x}/{y}.png' })
    expect(custom).toContain('https://*.tiles.example')
    expect(custom).not.toContain('openstreetmap')
  })

  it('is injected into index.html as a meta tag with quotes escaped', () => {
    const html = hostingPlugin({ onVercel: true, apiBase: API }).transformIndexHtml('<html><head><title>x</title></head></html>')
    expect(html).toMatch(/<head>\s*<meta http-equiv="Content-Security-Policy" content="default-src 'self'/)
    expect(html).toContain('connect-src')
  })
})

describe('vercel.json', () => {
  const cfg = JSON.parse(readFileSync(join(import.meta.dirname, '../../vercel.json'), 'utf8'))
  const rewrite = new RegExp(`^${cfg.rewrites[0].source.replace(/\\\\/g, '\\')}$`)

  it('builds with the repository scripts and serves the Vite output', () => {
    expect(cfg.buildCommand).toBe('npm run build && npm run verify:dist')
    expect(cfg.installCommand).toBe('npm ci')
    expect(cfg.outputDirectory).toBe('dist')
  })

  it('sends application routes to the SPA but never the API or missing assets', () => {
    for (const path of ['/w/abc/ai/datasets', '/login', '/register', '/w/1/assets/9', '/']) expect(rewrite.test(path), path).toBe(true)
    for (const path of ['/api/v1/me', '/api/v1/workspaces', '/assets/index-abc.js', '/favicon.svg']) expect(rewrite.test(path), path).toBe(false)
    expect(cfg.rewrites[0].destination).toBe('/index.html')
  })

  it('sets the baseline security headers and long-lived caching only for hashed assets', () => {
    const all = Object.fromEntries(cfg.headers[0].headers.map((h: { key: string; value: string }) => [h.key, h.value]))
    expect(all['X-Content-Type-Options']).toBe('nosniff')
    expect(all['X-Frame-Options']).toBe('DENY')
    expect(all['Strict-Transport-Security']).toMatch(/max-age=\d+/)
    expect(JSON.stringify(cfg.headers)).toContain('immutable')
    expect(cfg.headers.find((h: { source: string }) => h.source === '/assets/(.*)')).toBeTruthy()
    expect(cfg.headers.find((h: { source: string }) => h.source === '/index.html').headers[0].value).toBe('no-cache')
  })

  it('contains no secrets and no development addresses', () => {
    expect(JSON.stringify(cfg)).not.toMatch(/localhost|127\.0\.0\.1|secret|password|token/i)
  })
})

describe('verify-dist (post-build guard)', () => {
  const script = join(import.meta.dirname, '../../scripts/verify-dist.mjs')

  function dist(js: string, csp = `default-src 'self'; connect-src 'self' https://api.greenguardian.example`): string {
    const dir = mkdtempSync(join(tmpdir(), 'gg-dist-'))
    mkdirSync(join(dir, 'assets'))
    writeFileSync(join(dir, 'assets', 'app.js'), js)
    writeFileSync(join(dir, 'index.html'), `<html><head><meta http-equiv="Content-Security-Policy" content="${csp}" /></head></html>`)
    return dir
  }
  const run = (dir: string, env: Record<string, string> = {}) =>
    spawnSync(process.execPath, [script], { env: { ...process.env, DIST_DIR: dir, VITE_API_BASE_URL: '', VERCEL: '', ...env }, encoding: 'utf8' })

  it('passes a clean bundle that contains the configured API URL', () => {
    const r = run(dist(`fetch("${API}"); new URL("http://localhost")`), { VITE_API_BASE_URL: API, VERCEL: '1' })
    expect(r.status, r.stderr).toBe(0)
    expect(r.stdout).toContain('verify:dist ok')
  })

  it.each([
    ['a localhost address with a port', `fetch("http://localhost:8000/api/v1")`],
    ['a loopback IPv4 address', `fetch("http://127.0.0.1/api")`],
    ['0.0.0.0', `const h = "0.0.0.0"`],
    ['a reserved .invalid placeholder host', `fetch("https://api.greenguardian-preview.invalid/api/v1")`],
  ])('fails when the bundle contains %s', (_n, js) => {
    const r = run(dist(`${js};"${API}"`), { VITE_API_BASE_URL: API, VERCEL: '1' })
    expect(r.status).toBe(1)
    expect(r.stderr).toContain('verify:dist FAILED')
  })

  it('fails on a hosted build when the API URL is missing, not https, or absent from the bundle', () => {
    expect(run(dist('x'), { VERCEL: '1' }).stderr).toContain('missing or not an absolute https URL')
    expect(run(dist('x'), { VERCEL: '1', VITE_API_BASE_URL: 'http://api.example/api/v1' }).stderr).toContain('missing or not an absolute https URL')
    expect(run(dist('x'), { VERCEL: '1', VITE_API_BASE_URL: API }).stderr).toContain('not found in the JavaScript bundle')
  })

  it('fails when the CSP is missing, does not name the API origin, or is broader', () => {
    expect(run(dist(`"${API}"`, ''), { VERCEL: '1', VITE_API_BASE_URL: API }).stderr).toContain('no Content-Security-Policy')
    expect(run(dist(`"${API}"`, "default-src 'self'; connect-src 'self'"), { VERCEL: '1', VITE_API_BASE_URL: API }).stderr).toContain('does not allow exactly the API origin')
    const broad = `default-src 'self'; connect-src 'self' https://api.greenguardian.example https:`
    expect(run(dist(`"${API}"`, broad), { VERCEL: '1', VITE_API_BASE_URL: API }).stderr).toContain('broader than the single API origin')
  })
})
