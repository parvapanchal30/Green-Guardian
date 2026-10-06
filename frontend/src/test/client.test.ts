import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ProblemError, api, configureApi, tokenStore } from '../api/client'

const json = (status: number, body?: unknown) =>
  new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const pair = (n: number) => ({ access_token: `acc${n}`, refresh_token: `ref${n}`, token_type: 'bearer', expires_in: 900 })

describe('api client', () => {
  let lost: ReturnType<typeof vi.fn<() => void>>
  beforeEach(() => {
    lost = vi.fn<() => void>()
    configureApi({ baseUrl: '/api/v1', onAuthLost: lost })
    tokenStore.clear()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('maps problem+json to ProblemError including field errors', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(422, { code: 'validation_error', detail: 'bad', status: 422, errors: [{ loc: ['body', 'email'], msg: 'invalid', type: 'x' }] })))
    const err = (await api('/x', { method: 'POST', body: {}, auth: false }).catch((e) => e)) as ProblemError
    expect(err).toBeInstanceOf(ProblemError)
    expect(err.status).toBe(422)
    expect(err.code).toBe('validation_error')
    expect(err.fieldErrors[0]).toEqual({ loc: ['body', 'email'], msg: 'invalid' })
  })

  it('turns network failures into a readable ProblemError', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('failed') }))
    const err = (await api('/x').catch((e) => e)) as ProblemError
    expect(err.code).toBe('network_error')
    expect(err.message).toMatch(/Cannot reach the server/)
  })

  it('attaches the bearer token and returns undefined for 204', async () => {
    tokenStore.setTokens(pair(1))
    const f = vi.fn(async () => json(204))
    vi.stubGlobal('fetch', f)
    expect(await api('/y', { method: 'DELETE' })).toBeUndefined()
    const headers = (f.mock.calls[0] as unknown as [string, RequestInit])[1].headers as Headers
    expect(headers.get('Authorization')).toBe('Bearer acc1')
  })

  it('refreshes once on token_expired and retries; concurrent calls share one refresh', async () => {
    tokenStore.setTokens(pair(1))
    let refreshCalls = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
      const auth = (init.headers as Headers).get('Authorization')
      if (url.endsWith('/auth/refresh')) { refreshCalls++; return json(200, pair(2)) }
      return auth === 'Bearer acc2' ? json(200, { ok: true }) : json(401, { code: 'token_expired', detail: 'expired', status: 401 })
    }))
    const [a, b] = await Promise.all([api<{ ok: boolean }>('/a'), api<{ ok: boolean }>('/b')])
    expect(a.ok && b.ok).toBe(true)
    expect(refreshCalls).toBe(1)
    expect(tokenStore.refresh).toBe('ref2')
  })

  it('clears the session and signals auth loss when refresh fails', async () => {
    tokenStore.setTokens(pair(1))
    vi.stubGlobal('fetch', vi.fn(async (url: string) =>
      url.endsWith('/auth/refresh') ? json(401, { code: 'refresh_token_reuse', detail: 'used', status: 401 }) : json(401, { code: 'token_expired', detail: 'e', status: 401 })))
    await expect(api('/a')).rejects.toBeInstanceOf(ProblemError)
    expect(tokenStore.access).toBeNull()
    expect(tokenStore.refresh).toBeNull()
    expect(lost).toHaveBeenCalledTimes(1)
  })

  it('does not try to refresh on non-auth 401s (e.g. wrong password)', async () => {
    tokenStore.setTokens(pair(1))
    const f = vi.fn(async () => json(401, { code: 'invalid_credentials', detail: 'nope', status: 401 }))
    vi.stubGlobal('fetch', f)
    await expect(api('/auth/login', { method: 'POST', body: {}, auth: false })).rejects.toMatchObject({ code: 'invalid_credentials' })
    expect(f).toHaveBeenCalledTimes(1)
  })
})
