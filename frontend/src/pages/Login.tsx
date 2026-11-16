import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { HOME_BY_ROLE } from '../auth/roles'
import { DemoBanner } from '../components/Layout'
import { Alert, Button, Card, Spinner, TextField } from '../components/ui'

export function AuthShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <DemoBanner />
      <div className="mx-auto max-w-md px-4 py-10">
        <h1 className="mb-1 text-center text-2xl font-semibold text-indigo-700">InnerSpace</h1>
        <p className="mb-6 text-center text-sm text-slate-500">Seanslar arası defterin</p>
        <Card>
          <h2 className="mb-4 text-lg font-semibold">{title}</h2>
          {children}
        </Card>
      </div>
    </div>
  )
}

export function Login() {
  const { state, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (state.status === 'loading') return <Spinner />
  if (state.status === 'authed') return <Navigate to={HOME_BY_ROLE[state.user.role]} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const user = await login(email.trim(), password)
      navigate(HOME_BY_ROLE[user.role], { replace: true })
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Giriş yap">
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <TextField label="E-posta" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <TextField
          label="Parola"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? 'Giriş yapılıyor…' : 'Giriş yap'}
        </Button>
        <p className="text-center text-sm text-slate-600">
          Davet aldın mı?{' '}
          <Link to="/accept-invitation" className="font-medium text-indigo-700 underline">
            Daveti kabul et
          </Link>
        </p>
      </form>
    </AuthShell>
  )
}
