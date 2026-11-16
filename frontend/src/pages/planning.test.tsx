import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { tokens } from '../api/client'
import type { Appointment, Plan as PlanData, SharedPlan } from '../api/types'
import { CrisisScreen } from '../components/CrisisScreen'
import { mockFetch } from '../test/mockFetch'
import { Appointments } from './client/Appointments'
import { Moment } from './client/Moment'
import { Plan } from './client/Plan'
import { ClinicianClientDetail } from './clinician/ClientDetail'
import { ClinicianClients } from './clinician/Clinician'

afterEach(() => {
  tokens.clear()
  vi.unstubAllGlobals()
})

const future = new Date(Date.now() + 5 * 86400000).toISOString()
const past = new Date(Date.now() - 5 * 86400000).toISOString()
const appt = (over: Partial<Appointment>): Appointment => ({
  id: 'a1',
  client_id: 'c1',
  clinician_id: 'k1',
  clinician_name: 'Dr. Elif Kaya',
  kind: 'therapy',
  scheduled_at: future,
  ...over,
})

const PLAN: PlanData = {
  moment_steps: ['Nefes al', 'Birini ara'],
  self_note: 'Bu geçecek.',
  contacts: [{ name: 'Ablam', phone: '0555 000 00 01' }],
  warning_signs: ['Uykusuzluk'],
  coping_strategies: ['Yürüyüş'],
  talk_to_clinician: ['Atak'],
  shared_at: null,
  updated_at: '2026-11-16T10:00:00Z',
}

const inRouter = (ui: ReactNode) => render(<MemoryRouter>{ui}</MemoryRouter>)

describe('Randevularım', () => {
  it('splits upcoming and past and offers no way to change them', async () => {
    mockFetch({ 'GET /appointments': { body: [appt({ id: 'a1' }), appt({ id: 'a2', scheduled_at: past })] } })
    inRouter(<Appointments />)
    const upcoming = await screen.findByRole('region', { name: 'Yaklaşan' })
    expect(within(upcoming).getByText(/Dr. Elif Kaya/)).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Geçmiş' })).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows an empty state', async () => {
    mockFetch({ 'GET /appointments': { body: [] } })
    inRouter(<Appointments />)
    expect(await screen.findByText('Henüz randevu yok.')).toBeInTheDocument()
  })
})

describe('Planım', () => {
  it('saves the plan and shares/withdraws it with the clinician', async () => {
    const { calls } = mockFetch({
      'GET /plan': { body: PLAN },
      'PUT /plan': { body: PLAN },
      'POST /plan/share': { body: { ...PLAN, shared_at: '2026-11-17T09:00:00Z' } },
      'POST /plan/unshare': { body: PLAN },
    })
    inRouter(<Plan />)
    const u = userEvent.setup()
    expect(await screen.findByText(/uzmanınla birlikte hazırlamak/)).toBeInTheDocument()
    await u.click(screen.getByRole('button', { name: 'Planı kaydet' }))
    expect(await screen.findByText('Planın kaydedildi.')).toBeInTheDocument()
    const put = calls.find((c) => c.key === 'PUT /plan')!
    expect(JSON.parse(String(put.init.body)).moment_steps).toEqual(['Nefes al', 'Birini ara'])
    await u.click(screen.getByRole('button', { name: 'Uzmanımla paylaş' }))
    await u.click(await screen.findByRole('button', { name: 'Paylaşımı geri al' }))
    expect(await screen.findByRole('button', { name: 'Uzmanımla paylaş' })).toBeInTheDocument()
  })

  it('cannot share a plan that was never saved', async () => {
    mockFetch({ 'GET /plan': { body: { ...PLAN, moment_steps: [], contacts: [], updated_at: null } } })
    inRouter(<Plan />)
    expect(await screen.findByRole('button', { name: 'Uzmanımla paylaş' })).toBeDisabled()
  })

  it('shows the backend validation message', async () => {
    mockFetch({ 'GET /plan': { body: PLAN }, 'PUT /plan': { status: 422, body: { detail: [{ msg: 'telefon geçersiz' }] } } })
    inRouter(<Plan />)
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Planı kaydet' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('telefon geçersiz')
  })
})

describe('O an kartı', () => {
  it('shows steps, note, tel: links and 112', async () => {
    mockFetch({ 'GET /plan': { body: PLAN } })
    inRouter(<Moment />)
    expect(await screen.findByText('Nefes al')).toBeInTheDocument()
    expect(screen.getByText('Bu geçecek.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Ablam/ })).toHaveAttribute('href', 'tel:05550000001')
    expect(screen.getByRole('link', { name: /112/ })).toHaveAttribute('href', 'tel:112')
  })

  it('still offers 112 when there is no plan', async () => {
    mockFetch({ 'GET /plan': { body: { ...PLAN, moment_steps: [], self_note: '', contacts: [], updated_at: null } } })
    inRouter(<Moment />)
    expect(await screen.findByText(/Henüz bir planın yok/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /112/ })).toBeInTheDocument()
  })
})

describe('crisis screen with plan contacts', () => {
  it('adds the contacts and the O an link without changing the fixed text', () => {
    const crisis = {
      crisis: true,
      message: 'Sabit kriz mesajı.',
      resources: [{ name: 'Acil', contact: '112' }],
      contacts: [{ name: 'Ablam', phone: '0555 000 00 01' }],
    }
    inRouter(<CrisisScreen crisis={crisis} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Sabit kriz mesajı.')
    expect(screen.getByRole('link', { name: /Ablam/ })).toHaveAttribute('href', 'tel:05550000001')
    expect(screen.getByRole('link', { name: /O an/ })).toHaveAttribute('href', '/client/moment')
  })
})

const SHARED: SharedPlan = { ...PLAN, shared_at: '2026-11-17T09:00:00Z', updated_at: '2026-11-17T09:00:00Z' }

function renderClientDetail() {
  return render(
    <MemoryRouter initialEntries={['/clinician/clients/c1']}>
      <Routes>
        <Route path="/clinician/clients/:id" element={<ClinicianClientDetail />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('clinician client detail', () => {
  it('lists the next appointment on the client list', async () => {
    mockFetch({ 'GET /clinician/clients': { body: [{ id: 'c1', display_name: 'Ayşe Y.', next_appointment_at: future }] } })
    inRouter(<ClinicianClients />)
    expect(await screen.findByText(/Sonraki randevu/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ayşe Y.' })).toHaveAttribute('href', '/clinician/clients/c1')
  })

  it('creates, changes and cancels appointments and shows the shared plan read-only', async () => {
    vi.stubGlobal('confirm', () => true)
    const { calls } = mockFetch({
      'GET /clinician/clients': { body: [{ id: 'c1', display_name: 'Ayşe Y.', next_appointment_at: null }] },
      'GET /clinician/clients/c1/appointments': { body: [appt({ id: 'a1' })] },
      'GET /clinician/clients/c1/plan': { body: SHARED },
      'POST /clinician/clients/c1/appointments': { status: 201, body: appt({ id: 'a3' }) },
      'DELETE /clinician/appointments/a1': { status: 204 },
    })
    renderClientDetail()
    const u = userEvent.setup()
    expect(await screen.findByText(/Ablam/)).toBeInTheDocument()
    expect(screen.getByText(/Salt okunur/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Değiştir' })).toBeInTheDocument()

    await u.click(screen.getByRole('button', { name: 'Randevu oluştur' }))
    await u.type(screen.getByLabelText('Tarih ve saat'), '2026-12-01T10:30')
    await u.click(screen.getByRole('button', { name: 'Kaydet' }))
    await vi.waitFor(() => expect(calls.some((c) => c.key === 'POST /clinician/clients/c1/appointments')).toBe(true))

    await u.click(await screen.findByRole('button', { name: 'İptal et' }))
    await vi.waitFor(() => expect(calls.some((c) => c.key === 'DELETE /clinician/appointments/a1')).toBe(true))
  })

  it('says so when the client has not shared the plan', async () => {
    mockFetch({
      'GET /clinician/clients': { body: [] },
      'GET /clinician/clients/c1/appointments': { body: [] },
      'GET /clinician/clients/c1/plan': { status: 404, body: { detail: 'Plan not found' } },
    })
    renderClientDetail()
    expect(await screen.findByText('Danışan planını seninle paylaşmadı.')).toBeInTheDocument()
  })
})

describe('summary generation with an appointment', () => {
  it('sends only the appointment id so the backend derives the period', async () => {
    const { Summaries } = await import('./client/Summaries')
    const queued = {
      id: 'j1',
      status: 'queued',
      period_start: '2026-11-03',
      period_end: '2026-11-17',
      summary_id: null,
      error_code: null,
      attempts: 0,
      created_at: '',
      updated_at: '',
      crisis: null,
    }
    const { calls } = mockFetch({
      'GET /summaries': { body: [] },
      'GET /appointments': { body: [appt({ id: 'a1' })] },
      'POST /summaries/generate': { status: 202, body: queued },
      'GET /summaries/jobs/j1': { body: queued },
    })
    inRouter(<Summaries />)
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: 'Yeni özet' }))
    await u.selectOptions(await screen.findByLabelText(/Hangi randevu için/), 'a1')
    await u.click(screen.getByRole('button', { name: 'Özet taslağı oluştur' }))
    const post = calls.find((c) => c.key === 'POST /summaries/generate')!
    expect(JSON.parse(String(post.init.body))).toEqual({ appointment_id: 'a1' })
  })
})
