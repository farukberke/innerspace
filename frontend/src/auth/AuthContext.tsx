import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { refreshSession, setSessionExpiredHandler, tokens } from '../api/client'
import { authApi } from '../api/endpoints'
import type { DemoRole, User } from '../api/types'

type AuthState = { status: 'loading' } | { status: 'anon' } | { status: 'authed'; user: User }

interface AuthContextValue {
  state: AuthState
  login: (email: string, password: string) => Promise<User>
  demoLogin: (role: DemoRole) => Promise<User>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' })

  useEffect(() => {
    setSessionExpiredHandler(() => setState({ status: 'anon' }))
    return () => setSessionExpiredHandler(null)
  }, [])

  // Restore the session after a reload: the access token is memory-only, so use the refresh token.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        if (!tokens.refresh || !(await refreshSession())) throw new Error('no session')
        const user = await authApi.me()
        if (!cancelled) setState({ status: 'authed', user })
      } catch {
        if (!cancelled) setState({ status: 'anon' })
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    await authApi.login(email, password)
    const user = await authApi.me()
    setState({ status: 'authed', user })
    return user
  }, [])

  const demoLogin = useCallback(async (role: DemoRole) => {
    await authApi.demoLogin(role)
    const user = await authApi.me()
    setState({ status: 'authed', user })
    return user
  }, [])

  const logout = useCallback(() => {
    const refresh = tokens.refresh
    tokens.clear()
    void authApi.logout(refresh)
    setState({ status: 'anon' })
  }, [])

  const value = useMemo(() => ({ state, login, demoLogin, logout }), [state, login, demoLogin, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
