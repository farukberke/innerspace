import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from '../App'
import { tokens } from '../api/client'
import type { Appointment, ClientRead, Entry, Summary, User, UserRole } from '../api/types'
import { AuthProvider } from '../auth/AuthContext'
import { mockFetch } from '../test/mockFetch'
import { latestSummary, nextAppointment } from './client/Home'
import { sortClients } from './clinician/Clinician'

const pair = { access_token: 'a', refresh_token: 'r', token_type: 'bearer' }
const user = (role: UserRole, display_name = 'Ayşe Y.'): User => ({
  id: 'u1',
  organization_id: 'o1',
  email: 'x@example.test',
  display_name,
  role,
  is_active: true,
})

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

const daysFromNow = (n: number, hour = 14) => {
  const d = new Date()
  d.setDate(d.getDate() + n)
  d.setHours(hour, 0, 0, 0)
  return d.toISOString()
}

const appt = (over: Partial<Appointment>): Appointment => ({
  id: 'a1',
  client_id: 'u1',
  clinician_id: 'c1',
  clinician_name: 'Dr. Elif Kaya',
  kind: 'therapy',
  scheduled_at: daysFromNow(2),
  ...over,
})

const summary = (over: Partial<Summary>): Summary => ({
  id: 's1',
  client_id: 'u1',
  title: 'Seans öncesi özet',
  body: '',
  status: 'draft',
  period_start: '2026-11-01',
  period_end: '2026-11-14',
  statements: [{ id: 'st1', section: 'Atak kayıtları', text: 'Bu dönemde 2 atak kaydın var.', source_entry_ids: ['e1', 'e2'] }],
  approved_at: null,
  shared_at: null,
  created_at: '2026-11-15T10:00:00Z',
  appointment_id: null,
  topics: [],
  ...over,
})

const entry = (kind: Entry['kind'], daysAgo: number, details: Record<string, unknown>): Entry => ({
  id: `${kind}-${daysAgo}`,
  kind,
  occurred_at: daysFromNow(-daysAgo, 9),
  note: null,
  details,
  created_at: daysFromNow(-daysAgo, 9),
  updated_at: daysFromNow(-daysAgo, 9),
})

describe('one-click demo login', () => {
  it('offers the three roles when the backend enables it and signs in as the chosen one', async () => {
    const { calls } = mockFetch({
      'GET /auth/demo-login': { body: { enabled: true } },
      'POST /auth/demo-login': { body: pair },
      'GET /auth/me': { body: user('clinician', 'Dr. Elif Kaya') },
      'GET /clinician/clients': { body: [] },
    })
    renderAt('/login')
    expect(await screen.findByRole('button', { name: /Danışan olarak dene/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Yönetici olarak dene/ })).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: /Uzman olarak dene/ }))
    expect(await screen.findByRole('heading', { name: 'Danışanlarım' })).toBeInTheDocument()
    const login = calls.find((c) => c.key === 'POST /auth/demo-login')
    expect(JSON.parse(String(login?.init.body))).toEqual({ role: 'clinician' })
    expect(tokens.refresh).toBe('r')
  })

  it('shows only the password form when demo login is off or unknown', async () => {
    mockFetch({ 'GET /auth/demo-login': { body: { enabled: false } } })
    renderAt('/login')
    expect(await screen.findByLabelText('E-posta')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /olarak dene/ })).not.toBeInTheDocument()
  })

  it('shows the error when the demo account is unavailable', async () => {
    mockFetch({
      'GET /auth/demo-login': { body: { enabled: true } },
      'POST /auth/demo-login': { status: 404, body: { detail: 'Demo login is not available' } },
    })
    renderAt('/login')
    await userEvent.setup().click(await screen.findByRole('button', { name: /Danışan olarak dene/ }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(tokens.refresh).toBeNull()
  })
})

describe('client home', () => {
  it('shows the 21-day rhythm, the next appointment and the last summary', async () => {
    tokens.set(pair)
    mockFetch({
      'POST /auth/refresh': { body: pair },
      'GET /auth/me': { body: user('client') },
      'GET /reminders': { body: [] },
      'GET /entries': {
        body: {
          items: [entry('quick', 1, { sleep_hours: 6 }), entry('quick', 9, { sleep_hours: 7 }), entry('panic', 2, { intensity: 7 })],
          total: 3,
          limit: 100,
          offset: 0,
        },
      },
      'GET /appointments': { body: [appt({ id: 'past', scheduled_at: daysFromNow(-5) }), appt({ id: 'next' })] },
      'GET /summaries': { body: [summary({ id: 's-old', created_at: '2026-10-01T10:00:00Z', status: 'shared' }), summary({ id: 's-new' })] },
    })
    renderAt('/client/home')
    expect(await screen.findByRole('heading', { name: 'Merhaba Ayşe.' })).toBeInTheDocument()
    const rhythm = (await screen.findByRole('heading', { name: 'Son 21 gün' })).closest('section')!
    expect(await within(rhythm).findByText('Uyku ortalaması')).toBeInTheDocument()
    expect(within(rhythm).getByText('6,5 sa')).toBeInTheDocument()
    // Screen readers get the strip as a table.
    expect(within(rhythm).getByRole('table')).toHaveTextContent('7/10')

    const next = screen.getByRole('heading', { name: 'Sıradaki randevu' }).closest('section')!
    expect(within(next).getByRole('link', { name: /Seansa hazırlan/ })).toHaveAttribute('href', '/client/summaries?appointment=next')

    // The shared summary wins over a newer draft.
    const last = screen.getByRole('heading', { name: 'Son özet' }).closest('section')!
    expect(within(last).getByRole('link', { name: 'Seans öncesi özet' })).toHaveAttribute('href', '/client/summaries/s-old')
  })

  it('explains the empty states', async () => {
    tokens.set(pair)
    mockFetch({
      'POST /auth/refresh': { body: pair },
      'GET /auth/me': { body: user('client') },
      'GET /reminders': { body: [] },
      'GET /entries': { body: { items: [], total: 0, limit: 100, offset: 0 } },
      'GET /appointments': { body: [] },
      'GET /summaries': { body: [] },
    })
    renderAt('/client/home')
    expect(await screen.findByText('Planlı randevun yok.')).toBeInTheDocument()
    expect(await screen.findByText(/Bu dönemde uyku veya atak kaydın yok/)).toBeInTheDocument()
    expect(screen.getByText(/Henüz bir özetin yok/)).toBeInTheDocument()
  })

  it('picks the next future appointment and the summary to show', () => {
    const now = new Date()
    expect(nextAppointment([appt({ id: 'p', scheduled_at: daysFromNow(-1) }), appt({ id: 'b', scheduled_at: daysFromNow(9) }), appt({ id: 'a' })], now)?.id).toBe('a')
    expect(nextAppointment([], now)).toBeNull()
    expect(latestSummary([summary({ id: 'x', created_at: '2026-11-01T00:00:00Z' }), summary({ id: 'y', created_at: '2026-11-02T00:00:00Z' })])?.id).toBe('y')
  })
})

describe('clinician client list', () => {
  const client = (over: Partial<ClientRead>): ClientRead => ({
    id: 'c',
    display_name: 'X',
    next_appointment_at: null,
    last_shared_at: null,
    new_summaries: 0,
    ...over,
  })

  it('puts clients with new summaries first, then the soonest appointment', () => {
    const sorted = sortClients([
      client({ id: 'late', next_appointment_at: daysFromNow(5) }),
      client({ id: 'none' }),
      client({ id: 'new', new_summaries: 2, next_appointment_at: daysFromNow(9) }),
      client({ id: 'soon', next_appointment_at: daysFromNow(1) }),
    ])
    expect(sorted.map((c) => c.id)).toEqual(['new', 'soon', 'late', 'none'])
  })

  it('marks new summaries and shows the last share', async () => {
    tokens.set(pair)
    mockFetch({
      'POST /auth/refresh': { body: pair },
      'GET /auth/me': { body: user('clinician', 'Dr. Elif Kaya') },
      'GET /clinician/clients': {
        body: [
          client({ id: 'c1', display_name: 'Ayşe Y.', last_shared_at: daysFromNow(0, 9), new_summaries: 2 }),
          client({ id: 'c2', display_name: 'Can D.' }),
        ],
      },
    })
    renderAt('/clinician/clients')
    const ayse = await screen.findByRole('link', { name: /Ayşe Y\./ })
    expect(ayse).toHaveTextContent('2 yeni özet')
    expect(ayse).toHaveTextContent('bugün')
    expect(screen.getByRole('link', { name: /Can D\./ })).toHaveTextContent('Henüz paylaşım yok')
    expect(screen.getByText(/2 yeni paylaşılan özet var/)).toBeInTheDocument()
  })
})

describe('phone navigation', () => {
  it('keeps secondary pages and sign-out in the "Daha" sheet', async () => {
    tokens.set(pair)
    mockFetch({
      'POST /auth/refresh': { body: pair },
      'GET /auth/me': { body: user('client') },
      'GET /reminders': { body: [] },
      'GET /entries': { body: { items: [], total: 0, limit: 100, offset: 0 } },
      'GET /appointments': { body: [] },
      'GET /summaries': { body: [] },
      'POST /auth/logout': { status: 204 },
    })
    renderAt('/client/home')
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: 'Daha' }))
    const sheet = screen.getByRole('dialog', { name: 'Menü' })
    expect(within(sheet).getByRole('link', { name: 'Randevularım' })).toHaveAttribute('href', '/client/appointments')
    expect(within(sheet).getByRole('link', { name: 'Hesabım' })).toBeInTheDocument()
    await u.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await u.click(screen.getByRole('button', { name: 'Daha' }))
    await u.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Çıkış yap' }))
    expect(await screen.findByRole('heading', { name: 'Giriş yap' })).toBeInTheDocument()
  })
})
