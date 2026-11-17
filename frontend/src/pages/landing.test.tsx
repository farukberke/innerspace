import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from '../App'
import { tokens } from '../api/client'
import { AuthProvider } from '../auth/AuthContext'
import { mockFetch } from '../test/mockFetch'

afterEach(() => {
  tokens.clear()
  vi.unstubAllGlobals()
})

function renderHome() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('landing page', () => {
  it('shows the h1, the sign-in link and the synthetic-data warning to anonymous visitors', async () => {
    renderHome()
    expect(await screen.findByRole('heading', { level: 1, name: /Seanslar arası defter/ })).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent('yalnızca sentetik veri')
    expect(screen.getAllByRole('link', { name: /Giriş yap/ })[0]).toHaveAttribute('href', '/login')
    expect(screen.getByRole('link', { name: 'İçeriğe geç' })).toHaveAttribute('href', '#main')
  })

  it('sends a signed-in user to their home instead', async () => {
    tokens.set({ access_token: 'a', refresh_token: 'r', token_type: 'bearer' })
    mockFetch({
      'POST /auth/refresh': { body: { access_token: 'a2', refresh_token: 'r', token_type: 'bearer' } },
      'GET /auth/me': {
        body: { id: 'u', organization_id: 'o', email: 'x@example.test', display_name: 'T', role: 'org_admin', is_active: true },
      },
      'GET /admin/users': { body: [] },
    })
    renderHome()
    expect(await screen.findByRole('heading', { name: 'Kullanıcılar' })).toBeInTheDocument()
  })
})
