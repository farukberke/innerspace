import { useEffect, useRef, useState, type ComponentType, type SVGProps } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import type { UserRole } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { HOME_BY_ROLE, ROLE_LABEL } from '../auth/roles'
import {
  CalendarIcon,
  CloseIcon,
  LinkIcon,
  LogoutIcon,
  MenuIcon,
  NotebookIcon,
  PenIcon,
  PlanIcon,
  SummaryIcon,
  TodayIcon,
  UserIcon,
  UsersIcon,
} from './icons'

export function DemoBanner({ className = '' }: { className?: string }) {
  return (
    <div role="note" className={`bg-warn-100 px-4 py-2 text-center text-[0.8125rem] font-semibold text-warn-900 ${className}`}>
      Demo — yalnızca sentetik veri. Gerçek kişisel veya sağlık bilgisi girme.
    </div>
  )
}

export function SkipLink() {
  return (
    <a href="#main" className="skip-link">
      İçeriğe geç
    </a>
  )
}

/** The brand mark: an attack disc and a sleep bar, the two marks the product is built around. */
export function Logo({ inverted = false, className = '' }: { inverted?: boolean; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <svg viewBox="0 0 28 28" width="28" height="28" aria-hidden className="shrink-0">
        <circle cx="10" cy="11" r="8" fill="var(--color-attack)" />
        <rect x="16" y="13" width="9" height="13" rx="1.5" fill="var(--color-sleep)" />
      </svg>
      <span className={`text-[1.375rem] font-extrabold tracking-tight [font-stretch:118%] ${inverted ? 'text-white' : 'text-ink'}`}>
        InnerSpace
      </span>
    </span>
  )
}

type IconType = ComponentType<SVGProps<SVGSVGElement>>
interface NavItem {
  to: string
  label: string
  icon: IconType
  /** Shown in the phone tab bar; the rest live in the "Daha" sheet. */
  primary?: boolean
}

export const NAV: Record<UserRole, NavItem[]> = {
  client: [
    { to: '/client/home', label: 'Bugün', icon: TodayIcon, primary: true },
    { to: '/client/entries', label: 'Kayıtlarım', icon: NotebookIcon, primary: true },
    { to: '/client/summaries', label: 'Özetlerim', icon: SummaryIcon, primary: true },
    { to: '/client/plan', label: 'Planım', icon: PlanIcon, primary: true },
    { to: '/client/appointments', label: 'Randevularım', icon: CalendarIcon },
    { to: '/client/after-session', label: 'Seans sonrası', icon: PenIcon },
    { to: '/client/account', label: 'Hesabım', icon: UserIcon },
  ],
  clinician: [
    { to: '/clinician/clients', label: 'Danışanlarım', icon: UsersIcon, primary: true },
    { to: '/clinician/summaries', label: 'Paylaşılan özetler', icon: SummaryIcon, primary: true },
  ],
  org_admin: [
    { to: '/admin/users', label: 'Kullanıcılar', icon: UsersIcon, primary: true },
    { to: '/admin/assignments', label: 'Atamalar', icon: LinkIcon, primary: true },
  ],
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter((p) => /\p{L}/u.test(p[0] ?? ''))
    .slice(0, 2)
    .map((p) => p[0]!.toLocaleUpperCase('tr-TR'))
    .join('')
}

/** The "O an" card: the client's own plan for a hard moment. Present everywhere, never alarming. */
function MomentButton({ withHint = false, className = '' }: { withHint?: boolean; className?: string }) {
  return (
    <Link
      to="/client/moment"
      aria-label="O an: zor bir an için planın"
      className={`btn inline-flex min-h-11 flex-col items-start justify-center rounded-soft border border-danger-200 bg-danger-50 px-4 py-1.5 leading-tight text-danger-800 hover:bg-danger-100 ${className}`}
    >
      <span className="text-base font-extrabold">O an</span>
      {withHint && <span className="text-[0.8125rem] font-semibold text-danger-700">Zor bir an için planın</span>}
    </Link>
  )
}

/** Phone "Daha" sheet: secondary destinations, who is signed in, and sign-out. */
function MoreSheet({ items, onClose }: { items: NavItem[]; onClose: () => void }) {
  const { state, logout } = useAuth()
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
    }
  }, [onClose])
  if (state.status !== 'authed') return null
  return (
    <div className="fixed inset-0 z-40 lg:hidden">
      <button type="button" aria-label="Menüyü kapat" tabIndex={-1} className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Menü"
        className="sheet absolute inset-x-0 bottom-0 rounded-t-2xl bg-surface px-4 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-3 shadow-[0_-8px_32px_rgba(21,23,42,0.18)]"
      >
        <div className="flex items-center justify-between gap-3 pb-2">
          <div className="flex min-w-0 items-center gap-3">
            <span aria-hidden className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-brand-600 text-sm font-bold text-white">
              {initials(state.user.display_name)}
            </span>
            <div className="min-w-0 leading-tight">
              <div className="truncate font-bold">{state.user.display_name}</div>
              <div className="text-[0.8125rem] text-muted">{ROLE_LABEL[state.user.role]}</div>
            </div>
          </div>
          <button ref={closeRef} type="button" onClick={onClose} className="grid h-11 w-11 place-items-center rounded-soft hover:bg-sunk" aria-label="Kapat">
            <CloseIcon />
          </button>
        </div>
        {items.length > 0 && (
          <ul className="border-t border-line py-2">
            {items.map((n) => (
              <li key={n.to}>
                <NavLink
                  to={n.to}
                  onClick={onClose}
                  className={({ isActive }) =>
                    `flex min-h-12 items-center gap-3 rounded-soft px-3 text-base font-semibold ${isActive ? 'bg-brand-50 text-brand-700' : 'text-ink hover:bg-sunk'}`
                  }
                >
                  <n.icon />
                  {n.label}
                </NavLink>
              </li>
            ))}
          </ul>
        )}
        <button
          type="button"
          onClick={logout}
          className="flex min-h-12 w-full items-center gap-3 rounded-soft border-t border-line px-3 text-base font-semibold text-ink hover:bg-sunk"
        >
          <LogoutIcon />
          Çıkış yap
        </button>
      </div>
    </div>
  )
}

export function Layout() {
  const { state, logout } = useAuth()
  const [moreOpen, setMoreOpen] = useState(false)
  const location = useLocation()
  // Navigation closes the sheet (also covers the browser back button).
  const [lastPath, setLastPath] = useState(location.pathname)
  if (lastPath !== location.pathname) {
    setLastPath(location.pathname)
    setMoreOpen(false)
  }
  if (state.status !== 'authed') return null
  const { user } = state
  const items = NAV[user.role]
  const primary = items.filter((n) => n.primary)
  const secondary = items.filter((n) => !n.primary)
  const secondaryActive = secondary.some((n) => location.pathname.startsWith(n.to))

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[16.5rem_1fr]">
      <SkipLink />

      {/* Desktop: the cobalt rail. */}
      <aside className="sticky top-0 hidden h-screen flex-col bg-brand-600 px-4 pb-5 pt-6 text-white lg:flex">
        <Link to={HOME_BY_ROLE[user.role]} className="mb-8 px-2">
          <Logo inverted />
        </Link>
        <nav aria-label="Ana menü">
          <ul className="space-y-1">
            {items.map((n) => (
              <li key={n.to}>
                <NavLink
                  to={n.to}
                  className={({ isActive }) =>
                    `flex min-h-11 items-center gap-3 rounded-soft px-3 text-[0.9375rem] font-semibold transition-colors ${
                      isActive ? 'bg-white text-brand-700' : 'text-brand-50 hover:bg-white/10 hover:text-white'
                    }`
                  }
                >
                  <n.icon />
                  {n.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="mt-auto space-y-4">
          {user.role === 'client' && <MomentButton withHint className="w-full" />}
          <div className="flex items-center gap-3 border-t border-white/20 pt-4">
            <span aria-hidden className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-white/15 text-[0.8125rem] font-bold">
              {initials(user.display_name)}
            </span>
            <div className="min-w-0 flex-1 leading-tight">
              <div className="truncate text-[0.9375rem] font-bold">{user.display_name}</div>
              <div className="text-[0.8125rem] text-brand-100">{ROLE_LABEL[user.role]}</div>
            </div>
            <button type="button" onClick={logout} className="grid h-11 w-11 place-items-center rounded-soft text-brand-50 hover:bg-white/10 hover:text-white" aria-label="Çıkış">
              <LogoutIcon />
            </button>
          </div>
        </div>
      </aside>

      <div className="min-w-0">
        <DemoBanner />
        {/* Phone/tablet: slim top bar; destinations live in the bottom tab bar. */}
        <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-line bg-paper/95 px-4 py-2.5 backdrop-blur lg:hidden">
          <Link to={HOME_BY_ROLE[user.role]} aria-label="InnerSpace ana sayfa">
            <Logo />
          </Link>
          {user.role === 'client' && <MomentButton />}
        </header>

        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl px-4 pb-28 pt-6 focus:outline-none sm:px-6 sm:pt-8 lg:px-10 lg:pb-16 lg:pt-10">
          <Outlet />
        </main>

        <nav aria-label="Ana menü" className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden">
          <ul className="mx-auto grid max-w-lg" style={{ gridTemplateColumns: `repeat(${primary.length + 1}, minmax(0, 1fr))` }}>
            {primary.map((n) => (
              <li key={n.to}>
                <NavLink
                  to={n.to}
                  className={({ isActive }) =>
                    `flex min-h-16 flex-col items-center justify-center gap-1 px-1 text-[0.75rem] font-semibold leading-none ${
                      isActive ? 'text-brand-700' : 'text-muted hover:text-ink'
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      <span className={`grid h-7 w-12 place-items-center rounded-full ${isActive ? 'bg-brand-100' : ''}`}>
                        <n.icon />
                      </span>
                      <span className="max-w-full truncate">{n.label}</span>
                    </>
                  )}
                </NavLink>
              </li>
            ))}
            <li>
              <button
                type="button"
                aria-haspopup="dialog"
                aria-expanded={moreOpen}
                onClick={() => setMoreOpen(true)}
                className={`flex min-h-16 w-full flex-col items-center justify-center gap-1 px-1 text-[0.75rem] font-semibold leading-none ${
                  secondaryActive ? 'text-brand-700' : 'text-muted hover:text-ink'
                }`}
              >
                <span className={`grid h-7 w-12 place-items-center rounded-full ${secondaryActive ? 'bg-brand-100' : ''}`}>
                  <MenuIcon />
                </span>
                Daha
              </button>
            </li>
          </ul>
        </nav>
        {moreOpen && <MoreSheet items={secondary} onClose={() => setMoreOpen(false)} />}
      </div>
    </div>
  )
}
