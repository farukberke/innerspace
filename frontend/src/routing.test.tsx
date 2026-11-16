import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { tokens } from './api/client'
import type { User, UserRole } from './api/types'
import { AuthProvider } from './auth/AuthContext'
import { mockFetch } from './test/mockFetch'

const user = (role: UserRole): User => ({
  id: 'u1',
  organization_id: 'o1',
  email: 'x@example.test',
  display_name: 'Test Kişi',
  role,
  is_active: true,
})
const pair = { access_token: 'a', refresh_token: 'r', token_type: 'bearer' }
const emptyPage = { items: [], total: 0, limit: 10, offset: 0 }

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => {
  tokens.clear()
  vi.unstubAllGlobals()
})

describe('role based routing', () => {
  it('sends anonymous visitors to the login page, with the demo banner', async () => {
    renderAt('/client/entries')
    expect(await screen.findByRole('heading', { name: 'Giriş yap' })).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent('yalnızca sentetik veri')
  })

  it.each([
    ['client', 'Kayıtlarım', { 'GET /entries': { body: emptyPage } }],
    ['clinician', 'Danışanlarım', { 'GET /clinician/clients': { body: [] } }],
    ['org_admin', 'Kullanıcılar', { 'GET /admin/users': { body: [] } }],
  ] as const)('login as %s lands on that role home', async (role, heading, extra) => {
    mockFetch({
      'POST /auth/login': { body: pair },
      'GET /auth/me': { body: user(role) },
      ...extra,
    })
    renderAt('/login')
    const u = userEvent.setup()
    await u.type(await screen.findByLabelText('E-posta'), 'x@example.test')
    await u.type(screen.getByLabelText('Parola'), 'correct horse battery')
    await u.click(screen.getByRole('button', { name: 'Giriş yap' }))
    expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument()
  })

  it('shows an error for wrong credentials', async () => {
    mockFetch({ 'POST /auth/login': { status: 401, body: { detail: 'Invalid email or password' } } })
    renderAt('/login')
    const u = userEvent.setup()
    await u.type(await screen.findByLabelText('E-posta'), 'x@example.test')
    await u.type(screen.getByLabelText('Parola'), 'wrong')
    await u.click(screen.getByRole('button', { name: 'Giriş yap' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('hatalı')
  })

  it('restores the session from the refresh token and keeps a clinician off client pages', async () => {
    tokens.set(pair)
    mockFetch({
      'POST /auth/refresh': { body: { ...pair, access_token: 'a2' } },
      'GET /auth/me': { body: user('clinician') },
      'GET /clinician/clients': { body: [{ id: 'c1', display_name: 'Danışan Bir' }] },
    })
    renderAt('/client/entries')
    expect(await screen.findByRole('heading', { name: 'Danışanlarım' })).toBeInTheDocument()
    // The heading renders before the client list request resolves: wait for the list itself.
    expect(await screen.findByText('Danışan Bir')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Kayıtlarım' })).not.toBeInTheDocument()
  })

  it('does not show admin pages to a client', async () => {
    tokens.set(pair)
    mockFetch({
      'POST /auth/refresh': { body: pair },
      'GET /auth/me': { body: user('client') },
      'GET /entries': { body: emptyPage },
    })
    renderAt('/admin/users')
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Kayıtlarım' })).toBeInTheDocument())
  })

  it('logs out back to the login page', async () => {
    tokens.set(pair)
    mockFetch({
      'POST /auth/refresh': { body: pair },
      'GET /auth/me': { body: user('clinician') },
      'GET /clinician/clients': { body: [] },
    })
    renderAt('/clinician/clients')
    const u = userEvent.setup()
    await screen.findByRole('heading', { name: 'Danışanlarım' })
    await u.click(screen.getAllByRole('button', { name: 'Çıkış' })[0])
    expect(await screen.findByRole('heading', { name: 'Giriş yap' })).toBeInTheDocument()
    expect(tokens.refresh).toBeNull()
  })
})
