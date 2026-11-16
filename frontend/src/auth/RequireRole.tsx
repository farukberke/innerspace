import { Navigate, Outlet } from 'react-router-dom'
import { Spinner } from '../components/ui'
import type { UserRole } from '../api/types'
import { useAuth } from './AuthContext'
import { HOME_BY_ROLE } from './roles'

/** Route guard: anonymous -> /login; wrong role -> that role's own home. */
export function RequireRole({ role }: { role: UserRole }) {
  const { state } = useAuth()
  if (state.status === 'loading') return <Spinner />
  if (state.status === 'anon') return <Navigate to="/login" replace />
  if (state.user.role !== role) return <Navigate to={HOME_BY_ROLE[state.user.role]} replace />
  return <Outlet />
}

/** "/" and unknown paths: send the visitor to their role's home. */
export function HomeRedirect() {
  const { state } = useAuth()
  if (state.status === 'loading') return <Spinner />
  if (state.status === 'anon') return <Navigate to="/login" replace />
  return <Navigate to={HOME_BY_ROLE[state.user.role]} replace />
}
