import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { HOME_BY_ROLE } from '../auth/roles'
import { DemoBanner, Logo, SkipLink } from '../components/Layout'
import { Alert, Button, Spinner, TextField } from '../components/ui'

/** The illustration beside every auth form: the room the notebook prepares for. */
function RoomPanel() {
  return (
    <div className="relative hidden overflow-hidden bg-sunk lg:block">
      <img src="/login-room.webp" alt="" width={1024} height={1536} className="absolute inset-0 h-full w-full object-cover object-bottom" />
      <p className="absolute left-12 right-12 top-14 max-w-[14ch] text-[2.5rem] font-extrabold leading-[1.05] text-ink">
        Seanslar arası defterin.
      </p>
    </div>
  )
}

export function AuthShell({ title, lede, children }: { title: string; lede?: ReactNode; children: ReactNode }) {
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <SkipLink />
      <RoomPanel />
      <div className="flex min-h-screen flex-col">
        <DemoBanner />
        <main id="main" tabIndex={-1} className="mx-auto flex w-full max-w-[30rem] flex-1 flex-col px-5 pb-12 pt-8 focus:outline-none sm:pt-14">
          <Link to="/" className="mb-10 flex min-h-11 items-center self-start" aria-label="Seans Arası tanıtım sayfası">
            <Logo />
          </Link>
          <h1 className="text-[2.25rem] leading-[1.05] sm:text-[2.75rem]">{title}</h1>
          {lede && <p className="mt-3 text-base text-ink-2">{lede}</p>}
          <div className="mt-8">{children}</div>
        </main>
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
    <AuthShell title="Giriş yap" lede="Danışan, uzman veya klinik yöneticisi olarak.">
      {error && (
        <div className="mb-5">
          <Alert>{error}</Alert>
        </div>
      )}
      <form onSubmit={submit} className="space-y-4" aria-label="E-postayla giriş">
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
        <p className="text-center text-[0.9375rem] text-ink-2">
          Davet aldın mı?{' '}
          <Link to="/accept-invitation" className="link inline-flex min-h-11 items-center">
            Daveti kabul et
          </Link>
        </p>
      </form>
    </AuthShell>
  )
}
