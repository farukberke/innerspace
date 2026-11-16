import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, errorMessage, request, setSessionExpiredHandler, tokens } from './client'
import { mockFetch } from '../test/mockFetch'

const pair = (n: string) => ({ access_token: `a-${n}`, refresh_token: `r-${n}`, token_type: 'bearer' })

afterEach(() => {
  tokens.clear()
  setSessionExpiredHandler(null)
  vi.unstubAllGlobals()
})

describe('request', () => {
  it('sends the bearer token and keeps it out of the URL', async () => {
    tokens.set(pair('1'))
    const { calls, fn } = mockFetch({ 'GET /auth/me': { body: { ok: true } } })
    await request('/auth/me')
    const headers = calls[0].init.headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer a-1')
    expect(String(fn.mock.calls[0][0])).not.toContain('a-1')
  })

  it('on 401 refreshes once and retries with the new token', async () => {
    tokens.set(pair('1'))
    let n = 0
    const { calls } = mockFetch({
      'GET /entries': (_u, init) => {
        n += 1
        const auth = (init.headers as Record<string, string>).Authorization
        return auth === 'Bearer a-2' ? { body: { items: [] } } : { status: 401, body: { detail: 'x' } }
      },
      'POST /auth/refresh': { body: pair('2') },
    })
    const res = await request<{ items: unknown[] }>('/entries')
    expect(res.items).toEqual([])
    expect(n).toBe(2)
    expect(calls.map((c) => c.key)).toEqual(['GET /entries', 'POST /auth/refresh', 'GET /entries'])
    expect(tokens.refresh).toBe('r-2')
  })

  it('shares one refresh between concurrent 401s', async () => {
    tokens.set(pair('1'))
    const { calls } = mockFetch({
      'GET /entries': (_u, init) =>
        (init.headers as Record<string, string>).Authorization === 'Bearer a-2' ? { body: [] } : { status: 401 },
      'POST /auth/refresh': { body: pair('2') },
    })
    await Promise.all([request('/entries'), request('/entries')])
    expect(calls.filter((c) => c.key === 'POST /auth/refresh')).toHaveLength(1)
  })

  it('ends the session when refresh fails', async () => {
    tokens.set(pair('1'))
    const expired = vi.fn()
    setSessionExpiredHandler(expired)
    mockFetch({ 'GET /entries': { status: 401 }, 'POST /auth/refresh': { status: 401 } })
    await expect(request('/entries')).rejects.toBeInstanceOf(ApiError)
    expect(expired).toHaveBeenCalledOnce()
    expect(tokens.access).toBeNull()
    expect(tokens.refresh).toBeNull()
  })

  it('does not try to refresh for public endpoints (wrong password)', async () => {
    tokens.set(pair('1'))
    const { calls } = mockFetch({ 'POST /auth/login': { status: 401, body: { detail: 'Invalid email or password' } } })
    await expect(request('/auth/login', { method: 'POST', body: {}, auth: false })).rejects.toMatchObject({ status: 401 })
    expect(calls).toHaveLength(1)
    expect(tokens.refresh).toBe('r-1')
  })

  it('exposes Retry-After on 429', async () => {
    mockFetch({ 'POST /summaries/generate': { status: 429, body: { error_code: 'rate_limited' }, headers: { 'Retry-After': '90' } } })
    const err = (await request('/summaries/generate', { method: 'POST', body: {} }).catch((e) => e)) as ApiError
    expect(err.retryAfter).toBe(90)
    expect(errorMessage(err)).toContain('2 dakika')
  })
})

describe('errorMessage', () => {
  it('formats seconds for short waits', () => {
    expect(errorMessage(new ApiError(429, null, 12))).toContain('12 saniye')
  })
  it('has a generic 429 message without Retry-After', () => {
    expect(errorMessage(new ApiError(429, null, null))).toContain('biraz bekleyip')
  })
  it('shows the guardrail reason for 422 string details', () => {
    expect(errorMessage(new ApiError(422, 'Statement reads like a diagnosis'))).toContain('Statement reads like a diagnosis')
  })
  it('includes the request id for server errors', () => {
    expect(errorMessage(new ApiError(500, null, null, 'req-1'))).toContain('req-1')
  })
})
