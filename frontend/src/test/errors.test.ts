import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ProblemError, api, configureApi, tokenStore } from '../api/client'
import { errorMessage, waitText } from '../components/states'

const problem = (status: number, body: Record<string, unknown>, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/problem+json', ...headers } })

describe('problem details: request IDs and throttling', () => {
  beforeEach(() => { configureApi({ baseUrl: '/api/v1' }); tokenStore.clear() })
  afterEach(() => vi.unstubAllGlobals())

  it('keeps the request ID from the body, falling back to the response header', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => problem(500, { code: 'internal_error', detail: 'boom', status: 500, request_id: 'body-id-123456' }, { 'X-Request-ID': 'header-id-12345' })))
    expect(await api('/x', { auth: false }).catch((e) => e)).toMatchObject({ requestId: 'body-id-123456' })
    vi.stubGlobal('fetch', vi.fn(async () => problem(500, { code: 'internal_error', detail: 'boom', status: 500 }, { 'X-Request-ID': 'header-id-12345' })))
    expect(await api('/x', { auth: false }).catch((e) => e)).toMatchObject({ requestId: 'header-id-12345' })
  })

  it('reads the cooldown from the body or the Retry-After header', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => problem(429, { code: 'too_many_attempts', detail: 'slow down', status: 429, retry_after_s: 120 })))
    expect(await api('/auth/login', { method: 'POST', body: {}, auth: false }).catch((e) => e)).toMatchObject({ status: 429, retryAfterS: 120 })
    vi.stubGlobal('fetch', vi.fn(async () => problem(429, { code: 'too_many_attempts', detail: 'slow down', status: 429 }, { 'Retry-After': '45' })))
    expect(await api('/auth/login', { method: 'POST', body: {}, auth: false }).catch((e) => e)).toMatchObject({ retryAfterS: 45 })
  })

  it('does not treat a 429 as an expired session (no refresh attempt)', async () => {
    tokenStore.setTokens({ access_token: 'a', refresh_token: 'r', token_type: 'bearer', expires_in: 900 })
    const f = vi.fn(async () => problem(429, { code: 'too_many_attempts', detail: 'x', status: 429, retry_after_s: 10 }))
    vi.stubGlobal('fetch', f)
    await expect(api('/anything')).rejects.toMatchObject({ status: 429 })
    expect(f).toHaveBeenCalledTimes(1)
  })
})

describe('errorMessage', () => {
  it('tells people how long to wait when throttled, rounding up', () => {
    expect(errorMessage(new ProblemError(429, 'too_many_attempts', 'x', [], { retryAfterS: 600 }))).toBe('Too many attempts. Please wait 10 minutes and try again.')
    expect(errorMessage(new ProblemError(429, 'too_many_attempts', 'x', [], { retryAfterS: 61 }))).toMatch(/2 minutes/)
    expect(errorMessage(new ProblemError(429, 'too_many_attempts', 'x', [], { retryAfterS: 30 }))).toMatch(/30 seconds/)
    expect(errorMessage(new ProblemError(429, 'too_many_attempts', 'x'))).toMatch(/a little while/)
  })

  it('adds the reference to server errors only, and leaves ordinary errors alone', () => {
    expect(errorMessage(new ProblemError(500, 'internal_error', 'Something went wrong', [], { requestId: 'abc-12345678' }))).toBe('Something went wrong (reference abc-12345678)')
    expect(errorMessage(new ProblemError(500, 'internal_error', 'Something went wrong'))).toBe('Something went wrong')
    expect(errorMessage(new ProblemError(401, 'invalid_credentials', 'Invalid email or password', [], { requestId: 'abc-12345678' }))).toBe('Invalid email or password')
    expect(errorMessage(new Error('plain'))).toBe('plain')
  })

  it('formats waits', () => {
    expect(waitText(1)).toBe('1 second')
    expect(waitText(59)).toBe('59 seconds')
    expect(waitText(60)).toBe('1 minute')
    expect(waitText(3600)).toBe('60 minutes')
  })
})
