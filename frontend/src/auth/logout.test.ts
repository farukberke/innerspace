import { afterEach, describe, expect, it, vi } from 'vitest'
import { authApi } from '../api/endpoints'
import { tokens } from '../api/client'
import { mockFetch } from '../test/mockFetch'

afterEach(() => {
  tokens.clear()
  vi.unstubAllGlobals()
})

describe('authApi.logout', () => {
  it('sends the refresh token to the revoke endpoint without a bearer header', async () => {
    const { calls } = mockFetch({ 'POST /auth/logout': { status: 204 } })
    await authApi.logout('r-1')
    expect(calls.map((c) => c.key)).toEqual(['POST /auth/logout'])
    expect(JSON.parse(calls[0].init.body as string)).toEqual({ refresh_token: 'r-1' })
  })

  it('does not throw when the server call fails', async () => {
    mockFetch({ 'POST /auth/logout': { status: 500 } })
    await expect(authApi.logout('r-1')).resolves.toBeUndefined()
  })

  it('does nothing without a refresh token', async () => {
    const { calls } = mockFetch({})
    await authApi.logout(null)
    expect(calls).toHaveLength(0)
  })
})
