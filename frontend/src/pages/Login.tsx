import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { HOME_BY_ROLE } from '../auth/roles'
import { DemoBanner, SkipLink } from '../components/Layout'
import { Alert, Button, Card, Spinner, TextField } from '../components/ui'

export function AuthShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <SkipLink />
      <DemoBanner />
      <main id="main" tabIndex={-1} className="mx-auto max-w-md px-4 py-10 focus:outline-none sm:py-16">
        <p className="mb-1 text-center">
          <Link to="/" className="font-display text-3xl font-semibold text-brand-700">
            InnerSpace
          </Link>
        </p>
        <p className="mb-8 text-center text-base text-ink-2">Seanslar arası defterin</p>
        <Card>
          <h1 className="mb-5 text-2xl font-semibold">{title}</h1>
          {children}
        </Card>
      </main>
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
        <p className="text-center text-sm text-ink-2">
          Davet aldın mı?{' '}
          <Link to="/accept-invitation" className="link inline-flex min-h-11 items-center">
            Daveti kabul et
          </Link>
        </p>
      </form>
    </AuthShell>
  )
}
