import { useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ROLE_LABEL } from '../auth/roles'
import type { UserRole } from '../api/types'
import { HOME_BY_ROLE } from '../auth/roles'
import { Button, buttonCls } from './ui'

export function DemoBanner() {
  return (
    <div role="note" className="bg-warn-100 px-4 py-2 text-center text-sm font-medium text-warn-900">
      Demo — yalnızca sentetik veri. Gerçek kişisel veya sağlık bilgisi girme.
    </div>
  )
}

const NAV: Record<UserRole, { to: string; label: string }[]> = {
  client: [
    { to: '/client/entries', label: 'Kayıtlarım' },
    { to: '/client/summaries', label: 'Özetlerim' },
    { to: '/client/appointments', label: 'Randevularım' },
    { to: '/client/plan', label: 'Planım' },
    { to: '/client/after-session', label: 'Seans sonrası' },
    { to: '/client/account', label: 'Hesabım' },
  ],
  clinician: [
    { to: '/clinician/clients', label: 'Danışanlarım' },
    { to: '/clinician/summaries', label: 'Paylaşılan özetler' },
  ],
  org_admin: [
    { to: '/admin/users', label: 'Kullanıcılar' },
    { to: '/admin/assignments', label: 'Atamalar' },
  ],
}

export function SkipLink() {
  return (
    <a href="#main" className="skip-link">
      İçeriğe geç
    </a>
  )
}

export function Layout() {
  const { state, logout } = useAuth()
  const [open, setOpen] = useState(false)
  if (state.status !== 'authed') return null
  const { user } = state
  const link = ({ isActive }: { isActive: boolean }) =>
    `flex min-h-11 items-center rounded-soft px-3 py-2 text-base font-medium md:text-sm ${isActive ? 'bg-brand-100 text-brand-800' : 'text-ink-2 hover:bg-sunk'}`

  return (
    <div className="min-h-screen">
      <SkipLink />
      <DemoBanner />
      <header className="sticky top-0 z-30 border-b border-line bg-paper">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Link to={HOME_BY_ROLE[user.role]} className="font-display text-xl font-semibold text-brand-700">
            InnerSpace
          </Link>
          <div className="flex items-center gap-2 md:order-3">
            {user.role === 'client' && (
              <Link to="/client/moment" className={buttonCls('danger')}>
                O an
              </Link>
            )}
            <button
              type="button"
              className={`${buttonCls('secondary')} md:hidden`}
              aria-expanded={open}
              aria-controls="main-nav"
              onClick={() => setOpen((o) => !o)}
            >
              Menü
            </button>
            <div className="hidden items-center gap-3 md:flex">
              <div className="text-right text-xs leading-tight text-ink-2">
                <div className="font-semibold text-ink">{user.display_name}</div>
                <div>{ROLE_LABEL[user.role]}</div>
              </div>
              <Button variant="secondary" onClick={logout}>
                Çıkış
              </Button>
            </div>
          </div>
          <nav
            id="main-nav"
            aria-label="Ana menü"
            className={`${open ? 'flex' : 'hidden'} fixed inset-x-0 bottom-0 top-0 z-20 flex-col gap-1 overflow-y-auto bg-paper px-4 pb-6 pt-24 md:static md:z-auto md:flex md:flex-1 md:flex-row md:overflow-visible md:bg-transparent md:p-0 md:pl-6`}
          >
            {NAV[user.role].map((n) => (
              <NavLink key={n.to} to={n.to} className={link} onClick={() => setOpen(false)}>
                {n.label}
              </NavLink>
            ))}
            <div className="mt-4 flex flex-col gap-3 border-t border-line pt-4 md:hidden">
              <span className="text-sm text-ink-2">
                {user.display_name} · {ROLE_LABEL[user.role]}
              </span>
              <Button variant="secondary" onClick={logout} className="w-full">
                Çıkış
              </Button>
            </div>
          </nav>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="mx-auto max-w-6xl px-4 py-8 focus:outline-none sm:px-6">
        <Outlet />
      </main>
    </div>
  )
}
