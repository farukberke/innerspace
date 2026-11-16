import { vi } from 'vitest'

export interface MockReply {
  status?: number
  body?: unknown
  headers?: Record<string, string>
}
export type Handler = (url: URL, init: RequestInit) => MockReply | Promise<MockReply>

/** Replaces global fetch. Handlers are keyed "METHOD /path" (path without the /api/v1 prefix). */
export function mockFetch(routes: Record<string, Handler | MockReply>) {
  const calls: { key: string; init: RequestInit }[] = []
  const fn = vi.fn(async (input: URL | string, init: RequestInit = {}) => {
    const url = new URL(String(input))
    const key = `${init.method ?? 'GET'} ${url.pathname.replace('/api/v1', '')}`
    calls.push({ key, init })
    const route = routes[key]
    if (!route) throw new Error(`unmocked request: ${key}`)
    const reply = typeof route === 'function' ? await route(url, init) : route
    const status = reply.status ?? 200
    return new Response(status === 204 ? null : JSON.stringify(reply.body ?? {}), {
      status,
      headers: reply.headers,
    })
  })
  vi.stubGlobal('fetch', fn)
  return { fn, calls }
}
