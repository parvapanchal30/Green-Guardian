import type { ProblemBody, TokenPair } from './types'

/** An RFC 7807 problem returned by the API (or a synthetic one for network failures). */
export class ProblemError extends Error {
  status: number
  code: string
  fieldErrors: { loc: string[]; msg: string }[]
  constructor(status: number, code: string, detail: string, fieldErrors: { loc: string[]; msg: string }[] = []) {
    super(detail)
    this.name = 'ProblemError'
    this.status = status
    this.code = code
    this.fieldErrors = fieldErrors
  }
}

const REFRESH_KEY = 'gg.refresh'
const AUTH_CODES = new Set(['token_expired', 'invalid_token', 'missing_token'])

let baseUrl = (import.meta.env?.VITE_API_BASE_URL as string | undefined) ?? '/api/v1'
let accessToken: string | null = null
let onAuthLost: () => void = () => {}
let refreshing: Promise<void> | null = null

export function configureApi(opts: { baseUrl?: string; onAuthLost?: () => void }) {
  if (opts.baseUrl !== undefined) baseUrl = opts.baseUrl
  if (opts.onAuthLost) onAuthLost = opts.onAuthLost
}

export const tokenStore = {
  // Access token lives in memory only. The refresh token is kept in sessionStorage (cleared with the tab);
  // moving it to an httpOnly cookie is a planned hardening step (docs/FRONTEND_ARCHITECTURE.md).
  setTokens(t: TokenPair) {
    accessToken = t.access_token
    try {
      sessionStorage.setItem(REFRESH_KEY, t.refresh_token)
    } catch {
      /* storage unavailable: session will not survive a reload */
    }
  },
  clear() {
    accessToken = null
    try {
      sessionStorage.removeItem(REFRESH_KEY)
    } catch {
      /* ignore */
    }
  },
  get access() {
    return accessToken
  },
  get refresh(): string | null {
    try {
      return sessionStorage.getItem(REFRESH_KEY)
    } catch {
      return null
    }
  },
}

async function parseProblem(res: Response): Promise<ProblemError> {
  let body: Partial<ProblemBody> = {}
  try {
    body = await res.json()
  } catch {
    /* non-JSON error body */
  }
  return new ProblemError(
    res.status,
    body.code ?? 'http_error',
    body.detail ?? res.statusText ?? 'Request failed',
    (body.errors ?? []).map((e) => ({ loc: e.loc, msg: e.msg })),
  )
}

async function raw(path: string, init: RequestInit & { auth?: boolean }): Promise<Response> {
  const headers = new Headers(init.headers)
  // JSON by default; multipart bodies (FormData) must keep the browser-generated boundary header.
  if (init.body !== undefined && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (init.auth !== false && accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  try {
    return await fetch(`${baseUrl}${path}`, { ...init, headers })
  } catch {
    throw new ProblemError(0, 'network_error', 'Cannot reach the server. Check your connection and try again.')
  }
}

/** Single-flight refresh: concurrent 401s share one refresh call. */
export function refreshSession(): Promise<void> {
  if (!refreshing) {
    refreshing = (async () => {
      const rt = tokenStore.refresh
      if (!rt) throw new ProblemError(401, 'missing_token', 'Not signed in')
      const res = await raw('/auth/refresh', { method: 'POST', body: JSON.stringify({ refresh_token: rt }), auth: false })
      if (!res.ok) {
        tokenStore.clear()
        onAuthLost()
        throw await parseProblem(res)
      }
      tokenStore.setTokens((await res.json()) as TokenPair)
    })().finally(() => {
      refreshing = null
    })
  }
  return refreshing
}

/** Send a request, refreshing the session once on an expired token. Returns the raw Response (errors not yet thrown). */
async function send(path: string, init: RequestInit & { auth?: boolean }): Promise<Response> {
  let res = await raw(path, init)
  if (res.status === 401 && init.auth !== false) {
    const problem = await parseProblem(res.clone())
    if (AUTH_CODES.has(problem.code) && tokenStore.refresh) {
      await refreshSession()
      res = await raw(path, init)
    }
  }
  if (!res.ok) throw await parseProblem(res)
  return res
}

export async function api<T>(path: string, opts: { method?: string; body?: unknown; auth?: boolean } = {}): Promise<T> {
  const body = opts.body === undefined ? undefined : opts.body instanceof FormData ? opts.body : JSON.stringify(opts.body)
  const res = await send(path, { method: opts.method ?? 'GET', body, auth: opts.auth })
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

/** Fetch a protected binary (an image) with the bearer token; the caller turns it into a blob URL. */
export async function apiBlob(path: string): Promise<Blob> {
  return (await send(path, { method: 'GET' })).blob()
}
