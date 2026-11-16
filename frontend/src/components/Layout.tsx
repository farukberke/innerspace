import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ROLE_LABEL } from '../auth/roles'
import type { UserRole } from '../api/types'
import { Button } from './ui'

export function DemoBanner() {
  return (
    <div role="note" className="bg-amber-100 px-4 py-2 text-center text-xs font-medium text-amber-900 sm:text-sm">
      Demo — yalnızca sentetik veri. Gerçek kişisel veya sağlık bilgisi girme.
    </div>
  )
}

const NAV: Record<UserRole, { to: string; label: string }[]> = {
  client: [
    { to: '/client/entries', label: 'Kayıtlarım' },
    { to: '/client/summaries', label: 'Özetlerim' },
    { to: '/client/after-session', label: 'Seans sonrası' },
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

export function Layout() {
  const { state, logout } = useAuth()
  const [open, setOpen] = useState(false)
  if (state.status !== 'authed') return null
  const { user } = state
  const link = ({ isActive }: { isActive: boolean }) =>
    `block rounded-lg px-3 py-2 text-sm font-medium ${isActive ? 'bg-indigo-100 text-indigo-800' : 'text-slate-600 hover:bg-slate-100'}`

  return (
    <div className="min-h-screen">
      <DemoBanner />
      <header className="relative border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-3">
          <span className="text-lg font-semibold text-indigo-700">InnerSpace</span>
          <button
            type="button"
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm md:hidden"
            aria-expanded={open}
            aria-controls="main-nav"
            onClick={() => setOpen((o) => !o)}
          >
            Menü
          </button>
          <nav
            id="main-nav"
            aria-label="Ana menü"
            className={`${open ? 'flex' : 'hidden'} absolute left-0 right-0 top-full z-10 flex-col gap-1 border-b border-slate-200 bg-white p-3 md:static md:flex md:flex-row md:border-0 md:p-0`}
          >
            {NAV[user.role].map((n) => (
              <NavLink key={n.to} to={n.to} className={link} onClick={() => setOpen(false)}>
                {n.label}
              </NavLink>
            ))}
            <div className="mt-2 flex items-center justify-between border-t border-slate-200 pt-2 md:hidden">
              <span className="text-xs text-slate-600">
                {user.display_name} · {ROLE_LABEL[user.role]}
              </span>
              <Button variant="secondary" onClick={logout}>
                Çıkış
              </Button>
            </div>
          </nav>
          <div className="hidden items-center gap-3 md:flex">
            <div className="text-right text-xs leading-tight text-slate-600">
              <div className="font-medium text-slate-800">{user.display_name}</div>
              <div>{ROLE_LABEL[user.role]}</div>
            </div>
            <Button variant="secondary" onClick={logout}>
              Çıkış
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
