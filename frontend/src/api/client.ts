import type { TokenPair } from './types'

const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')
const API = `${BASE}/api/v1`
const REFRESH_KEY = 'innerspace.refresh'

export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown
  readonly retryAfter: number | null
  readonly requestId: string | null

  constructor(status: number, detail: unknown, retryAfter: number | null = null, requestId: string | null = null) {
    super(typeof detail === 'string' ? detail : `HTTP ${status}`)
    this.status = status
    this.detail = detail
    this.retryAfter = retryAfter
    this.requestId = requestId
  }
}

// Access token lives in memory only. The backend does not set cookies, so the refresh token is
// kept in sessionStorage (cleared when the tab closes); see README.
let accessToken: string | null = null
let onSessionExpired: (() => void) | null = null
let refreshing: Promise<boolean> | null = null

export const tokens = {
  get access(): string | null {
    return accessToken
  },
  get refresh(): string | null {
    return sessionStorage.getItem(REFRESH_KEY)
  },
  set(pair: TokenPair): void {
    accessToken = pair.access_token
    sessionStorage.setItem(REFRESH_KEY, pair.refresh_token)
  },
  clear(): void {
    accessToken = null
    sessionStorage.removeItem(REFRESH_KEY)
  },
}

export function setSessionExpiredHandler(fn: (() => void) | null): void {
  onSessionExpired = fn
}

async function parse(res: Response): Promise<unknown> {
  if (res.status === 204) return undefined
  const text = await res.text()
  if (!text) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

function toError(res: Response, body: unknown): ApiError {
  const obj = (body && typeof body === 'object' ? body : {}) as { detail?: unknown; request_id?: string }
  const ra = res.headers.get('Retry-After')
  const retryAfter = ra && Number.isFinite(Number(ra)) ? Number(ra) : null
  return new ApiError(res.status, obj.detail ?? body, retryAfter, obj.request_id ?? res.headers.get('X-Request-ID'))
}

/** Exchanges the refresh token for a new pair. One refresh at a time; false = no new session. */
export function refreshSession(): Promise<boolean> {
  if (refreshing) return refreshing
  const refresh = tokens.refresh
  if (!refresh) return Promise.resolve(false)
  refreshing = (async () => {
    try {
      const res = await fetch(`${API}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      })
      if (!res.ok) {
        // Only an explicit rejection ends the session; a 429/5xx may be transient.
        if (res.status === 401) tokens.clear()
        return false
      }
      tokens.set((await parse(res)) as TokenPair)
      return true
    } catch {
      return false
    } finally {
      refreshing = null
    }
  })()
  return refreshing
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: Record<string, string | number | undefined>
  headers?: Record<string, string>
  /** false = public endpoint: no bearer header, no refresh-and-retry on 401. */
  auth?: boolean
}

async function send(path: string, opts: RequestOptions): Promise<Response> {
  const url = new URL(`${API}${path}`)
  for (const [k, v] of Object.entries(opts.query ?? {})) {
    if (v !== undefined && v !== '') url.searchParams.set(k, String(v))
  }
  const headers: Record<string, string> = { ...opts.headers }
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  if (opts.auth !== false && accessToken) headers.Authorization = `Bearer ${accessToken}`
  return fetch(url, {
    method: opts.method ?? 'GET',
    headers,
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  })
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  let res = await send(path, opts)
  if (res.status === 401 && opts.auth !== false) {
    if (await refreshSession()) {
      res = await send(path, opts)
    }
    if (res.status === 401) {
      tokens.clear()
      onSessionExpired?.()
    }
  }
  const body = await parse(res)
  if (!res.ok) throw toError(res, body)
  return body as T
}

/** Turkish, user-facing text for an API failure. Backend detail strings are shown for 409/422. */
export function errorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return 'Beklenmeyen bir hata oluştu. Lütfen tekrar dene.'
  switch (err.status) {
    case 429: {
      const s = err.retryAfter
      if (s === null) return 'Çok fazla istek gönderdin. Lütfen biraz bekleyip tekrar dene.'
      if (s < 60) return `Çok fazla istek gönderdin. Lütfen yaklaşık ${Math.max(1, Math.ceil(s))} saniye sonra tekrar dene.`
      return `Çok fazla istek gönderdin. Lütfen yaklaşık ${Math.ceil(s / 60)} dakika sonra tekrar dene.`
    }
    case 401:
      return 'E-posta veya parola hatalı ya da oturumun geçersiz.'
    case 403:
      return 'Bu işlem için yetkin yok.'
    case 404:
      return 'Aradığın kayıt bulunamadı.'
    case 409:
      return typeof err.detail === 'string' ? `İşlem yapılamadı: ${err.detail}` : 'İşlem şu anki durumla çakışıyor.'
    case 422: {
      if (typeof err.detail === 'string') return `Metin kabul edilmedi: ${err.detail}`
      if (Array.isArray(err.detail)) {
        const first = err.detail[0] as { msg?: string } | undefined
        return `Girdi geçersiz${first?.msg ? `: ${first.msg}` : '.'}`
      }
      return 'Girdi geçersiz.'
    }
    case 502:
      return 'Şu anda güvenli bir sonuç üretilemedi. Lütfen daha sonra tekrar dene.'
    case 503:
      return 'Bu özellik şu anda kullanılamıyor.'
    default:
      return err.status >= 500
        ? `Sunucu hatası oluştu.${err.requestId ? ` (Hata kodu: ${err.requestId})` : ''}`
        : 'İstek başarısız oldu.'
  }
}
