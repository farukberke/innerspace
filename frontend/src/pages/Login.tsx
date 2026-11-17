import { useCallback, useState, type FormEvent, type ReactNode } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { authApi } from '../api/endpoints'
import type { DemoRole } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { HOME_BY_ROLE } from '../auth/roles'
import { ArrowIcon } from '../components/icons'
import { DemoBanner, Logo, SkipLink } from '../components/Layout'
import { Alert, Button, Spinner, TextField } from '../components/ui'
import { useLoad } from '../hooks/useLoad'

/** The poster panel beside every auth form: the product's marks at poster scale. */
function PosterPanel() {
  return (
    <div aria-hidden className="relative hidden overflow-hidden bg-brand-600 lg:block">
      <svg viewBox="0 0 600 900" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full">
        <circle cx="430" cy="250" r="170" fill="var(--color-attack)" />
        <circle cx="170" cy="470" r="70" fill="var(--color-attack)" />
        <rect x="70" y="600" width="70" height="300" fill="var(--color-sleep)" />
        <rect x="170" y="560" width="70" height="340" fill="var(--color-sleep)" />
        <rect x="270" y="660" width="70" height="240" fill="var(--color-sleep)" />
        <rect x="370" y="540" width="70" height="360" fill="var(--color-sleep)" />
        <rect x="470" y="620" width="70" height="280" fill="var(--color-sleep)" />
        <circle cx="300" cy="420" r="34" fill="none" stroke="#fff" strokeWidth="10" />
        <rect x="455" y="470" width="50" height="50" fill="var(--color-med)" />
      </svg>
      <p className="absolute left-12 right-12 top-14 text-[2.75rem] font-extrabold leading-[1.02] text-white [font-stretch:118%]">
        Seanslar arası defterin.
      </p>
    </div>
  )
}

export function AuthShell({ title, lede, children }: { title: string; lede?: ReactNode; children: ReactNode }) {
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <SkipLink />
      <PosterPanel />
      <div className="flex min-h-screen flex-col">
        <DemoBanner />
        <main id="main" tabIndex={-1} className="mx-auto flex w-full max-w-[30rem] flex-1 flex-col px-5 pb-12 pt-8 focus:outline-none sm:pt-14">
          <Link to="/" className="mb-10 self-start" aria-label="InnerSpace tanıtım sayfası">
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

const DEMO_CHOICES: { role: DemoRole; title: string; who: string; sees: string }[] = [
  { role: 'client', title: 'Danışan olarak dene', who: 'Ayşe Y.', sees: 'Kayıtlar, 21 günlük ritim, özet hazırlama ve paylaşma' },
  { role: 'clinician', title: 'Uzman olarak dene', who: 'Dr. Elif Kaya', sees: 'Danışan listesi, yeni paylaşılan özetler, randevular' },
  { role: 'org_admin', title: 'Yönetici olarak dene', who: 'Deniz Yönetici', sees: 'Kullanıcılar ve atamalar; klinik içerik yok' },
]

function DemoChoices({ onError }: { onError: (message: string | null) => void }) {
  const { demoLogin } = useAuth()
  const navigate = useNavigate()
  const [busy, setBusy] = useState<DemoRole | null>(null)

  async function enter(role: DemoRole) {
    setBusy(role)
    onError(null)
    try {
      const user = await demoLogin(role)
      navigate(HOME_BY_ROLE[user.role], { replace: true })
    } catch (err) {
      onError(errorMessage(err))
      setBusy(null)
    }
  }

  return (
    <section aria-labelledby="demo-title">
      <h2 id="demo-title" className="text-lg font-extrabold">
        Tek tıkla dene
      </h2>
      <p className="mt-1 text-[0.9375rem] text-ink-2">Hazır demo hesaplarıyla, parola gerekmeden. Hepsi aynı sentetik klinikte.</p>
      <ul className="mt-4 space-y-2">
        {DEMO_CHOICES.map((c) => (
          <li key={c.role}>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => enter(c.role)}
              className="btn group flex min-h-16 w-full items-center justify-between gap-4 rounded-soft-lg border border-ink/20 bg-surface px-4 py-3 text-left hover:border-brand-600 hover:bg-brand-50 disabled:opacity-60"
            >
              <span className="min-w-0">
                <span className="block text-base font-extrabold text-ink">{busy === c.role ? 'Giriş yapılıyor…' : c.title}</span>
                <span className="block text-[0.875rem] text-ink-2">
                  {c.who} · {c.sees}
                </span>
              </span>
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand-600 text-white transition-transform group-hover:translate-x-0.5">
                <ArrowIcon />
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function Login() {
  const { state, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Unknown or failed = no demo buttons; the password form always works.
  const demo = useLoad(useCallback(() => authApi.demoStatus().catch(() => ({ enabled: false })), []))

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

  const demoEnabled = demo.data?.enabled === true
  return (
    <AuthShell title="Giriş yap" lede="Danışan, uzman veya klinik yöneticisi olarak.">
      {error && (
        <div className="mb-5">
          <Alert>{error}</Alert>
        </div>
      )}
      {demoEnabled && (
        <>
          <DemoChoices onError={setError} />
          <div className="my-8 flex items-center gap-4 text-[0.875rem] font-semibold text-muted">
            <span className="h-px flex-1 bg-line" />
            ya da e-postayla
            <span className="h-px flex-1 bg-line" />
          </div>
        </>
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
        <Button type="submit" className="w-full" variant={demoEnabled ? 'secondary' : 'primary'} disabled={busy}>
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
