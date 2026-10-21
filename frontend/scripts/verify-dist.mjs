// Post-build guard: fails if the production bundle could send visitors to a development address, or if the API origin
// that was configured is not what ended up in the build. Run by `npm run verify:dist` (and by Vercel's build command).
//
// The bare string "http://localhost" is allowed: react-router uses it as a dummy base when parsing relative URLs; it is
// never a request target. A loopback host WITH a port, 127.x.x.x or 0.0.0.0 is not allowed.
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const defaultDist = new URL('../dist/', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const dist = (process.env.DIST_DIR ?? defaultDist).replace(/[\\/]*$/, '/') // DIST_DIR is for tests
const apiBase = process.env.VITE_API_BASE_URL ?? ''
const onVercel = Boolean(process.env.VERCEL)

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name)
    return statSync(p).isDirectory() ? walk(p) : [p]
  })
}

const files = walk(dist).filter((f) => /\.(js|css|html|map)$/.test(f))
const problems = []
const bad = [
  { re: /(localhost|\[::1\]):\d{2,5}/gi, why: 'a localhost address with a port' },
  { re: /\b127\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/g, why: 'a loopback IPv4 address' },
  { re: /\b0\.0\.0\.0\b/g, why: '0.0.0.0' },
  { re: /https?:\/\/[a-z0-9.-]+\.invalid\b/gi, why: 'a reserved .invalid placeholder host' },
]
for (const f of files) {
  const text = readFileSync(f, 'utf8')
  for (const { re, why } of bad) {
    const m = text.match(re)
    if (m) problems.push(`${f.slice(dist.length)} contains ${why}: ${[...new Set(m)].slice(0, 3).join(', ')}`)
  }
}

if (onVercel || apiBase) {
  const origin = (() => {
    try {
      return new URL(apiBase).origin
    } catch {
      return null
    }
  })()
  if (!origin || !origin.startsWith('https://')) {
    problems.push('VITE_API_BASE_URL is missing or not an absolute https URL')
  } else {
    const inBundle = files.some((f) => /\.js$/.test(f) && readFileSync(f, 'utf8').includes(apiBase))
    if (!inBundle) problems.push('the configured API URL was not found in the JavaScript bundle (a stale or mis-keyed variable?)')
    const html = readFileSync(join(dist, 'index.html'), 'utf8')
    const csp = html.match(/Content-Security-Policy"\s+content="([^"]*)"/)?.[1] ?? ''
    if (!csp) problems.push('index.html has no Content-Security-Policy')
    else {
      // connect-src may list only 'self' and the one API origin: any other source (a scheme, a wildcard, another host) is broader
      const sources = (csp.split(';').map((d) => d.trim().split(/\s+/)).find((d) => d[0] === 'connect-src') ?? []).slice(1)
      if (!sources.includes(origin)) problems.push(`the Content-Security-Policy does not allow exactly the API origin ${origin}`)
      if (sources.some((s) => s !== "'self'" && s !== origin)) problems.push('the Content-Security-Policy connect-src is broader than the single API origin')
    }
  }
}

if (problems.length) {
  console.error('verify:dist FAILED\n - ' + problems.join('\n - '))
  process.exit(1)
}
console.log(`verify:dist ok (${files.length} files checked${apiBase ? `, API origin ${new URL(apiBase).origin}` : ', no API URL configured'})`)
