import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { tokens } from '../api/client'
import type { Reminder, SharedSummary, Summary } from '../api/types'
import { ReminderStrip } from '../components/ReminderStrip'
import { mockFetch } from '../test/mockFetch'
import { Account } from './client/Account'
import { SummaryDetail } from './client/SummaryDetail'
import { ClinicianSummaryDetail } from './clinician/Clinician'

const logout = vi.fn()
vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({
    state: { status: 'authed', user: { id: 'c1', display_name: 'Ayşe', email: 'ayse@x.test', role: 'client' } },
    logout,
  }),
}))

afterEach(() => {
  tokens.clear()
  vi.unstubAllGlobals()
  logout.mockReset()
})

const summary = (over: Partial<Summary> = {}): Summary => ({
  id: 's1',
  client_id: 'c1',
  title: 'Özet',
  body: 'x',
  status: 'approved',
  period_start: '2026-11-01',
  period_end: '2026-11-14',
  statements: [],
  approved_at: null,
  shared_at: null,
  created_at: '2026-11-15T10:00:00Z',
  appointment_id: null,
  topics: [],
  ...over,
})

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={['/client/summaries/s1']}>
      <Routes>
        <Route path="/client/summaries/:id" element={<SummaryDetail />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('konuşmak istediğim konular', () => {
  it('lets the client add topics and sends them as a list', async () => {
    const saved = summary({ status: 'draft', topics: ['Uyku düzenim'] })
    const { calls } = mockFetch({
      'GET /summaries/s1': { body: summary() },
      'PUT /summaries/s1/topics': { body: saved },
    })
    renderDetail()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: 'Konu ekle' }))
    await u.type(screen.getByLabelText('Konu 1'), 'Uyku düzenim')
    await u.click(screen.getByRole('button', { name: 'Konuları kaydet' }))
    const section = await screen.findByRole('region', { name: 'Konuşmak istediğim konular' })
    expect(within(section).getByText('Uyku düzenim')).toBeInTheDocument()
    const put = calls.find((c) => c.key === 'PUT /summaries/s1/topics')!
    expect(JSON.parse(String(put.init.body))).toEqual({ topics: ['Uyku düzenim'] })
  })

  it('shows the guardrail rejection', async () => {
    mockFetch({
      'GET /summaries/s1': { body: summary() },
      'PUT /summaries/s1/topics': { status: 422, body: { detail: 'The text must not contain a diagnosis' } },
    })
    renderDetail()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: 'Konu ekle' }))
    await u.type(screen.getByLabelText('Konu 1'), 'bir şey')
    await u.click(screen.getByRole('button', { name: 'Konuları kaydet' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Metin kabul edilmedi')
  })

  it('shows the fixed crisis screen when the backend answers with the crisis response', async () => {
    mockFetch({
      'GET /summaries/s1': { body: summary() },
      'PUT /summaries/s1/topics': {
        body: { crisis: true, message: 'Sabit kriz mesajı.', resources: [{ name: 'Acil', contact: '112' }] },
      },
    })
    renderDetail()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: 'Konu ekle' }))
    await u.type(screen.getByLabelText('Konu 1'), 'bir şey')
    await u.click(screen.getByRole('button', { name: 'Konuları kaydet' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Sabit kriz mesajı')
  })

  it('does not offer editing while the summary is shared', async () => {
    mockFetch({ 'GET /summaries/s1': { body: summary({ status: 'shared', topics: ['Atak'] }) } })
    renderDetail()
    expect(await screen.findByText('Atak')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Konu/ })).not.toBeInTheDocument()
    expect(screen.getByText(/önce paylaşımı geri al/)).toBeInTheDocument()
  })

  it('is shown to the clinician only when the shared summary has topics', async () => {
    const shared: SharedSummary = {
      id: 's1',
      client_id: 'c1',
      title: 'Özet',
      body: 'gövde',
      period_start: null,
      period_end: null,
      shared_at: '2026-11-15T10:00:00Z',
      created_at: '2026-11-15T10:00:00Z',
      topics: ['İş stresi'],
    }
    mockFetch({ 'GET /clinician/summaries/s1': { body: shared } })
    render(
      <MemoryRouter initialEntries={['/clinician/summaries/s1']}>
        <Routes>
          <Route path="/clinician/summaries/:id" element={<ClinicianSummaryDetail />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(await screen.findByText('Danışanın konuşmak istediği konular')).toBeInTheDocument()
    expect(screen.getByText('İş stresi')).toBeInTheDocument()
  })
})

describe('AI ibaresi', () => {
  it('is shown on the client summary detail, outside the topics section', async () => {
    mockFetch({ 'GET /summaries/s1': { body: summary({ topics: ['Uyku'] }) } })
    renderDetail()
    const note = await screen.findByTestId('ai-disclaimer')
    expect(note).toHaveTextContent('Bu özet, kendi kayıtlarından AI ile düzenlenmiştir. Teşhis veya tedavi önerisi içermez.')
    expect(screen.getByRole('region', { name: 'Konuşmak istediğim konular' })).not.toContainElement(note)
  })

  it('is shown on the clinician shared summary', async () => {
    const shared: SharedSummary = {
      id: 's1',
      client_id: 'c1',
      title: 'Özet',
      body: 'gövde',
      period_start: null,
      period_end: null,
      shared_at: '2026-11-15T10:00:00Z',
      created_at: '2026-11-15T10:00:00Z',
      topics: [],
    }
    mockFetch({ 'GET /clinician/summaries/s1': { body: shared } })
    render(
      <MemoryRouter initialEntries={['/clinician/summaries/s1']}>
        <Routes>
          <Route path="/clinician/summaries/:id" element={<ClinicianSummaryDetail />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(await screen.findByTestId('ai-disclaimer')).toHaveTextContent('danışanın kendi kayıtlarından AI ile düzenlenmiştir')
  })
})

describe('hatırlatma şeridi', () => {
  const r = (over: Partial<Reminder>): Reminder => ({
    kind: 'prepare_summary',
    message: 'Yarın randevun var — hazırlanmak ister misin?',
    appointment_id: 'a1',
    scheduled_at: '2026-11-18T09:00:00Z',
    ...over,
  })

  it('links the preparation reminder to summary creation with the appointment selected', async () => {
    mockFetch({
      'GET /reminders': {
        body: [r({}), r({ kind: 'after_session_note', message: 'Dünkü seansın için kısa bir not?', appointment_id: 'a0' })],
      },
    })
    render(
      <MemoryRouter>
        <ReminderStrip />
      </MemoryRouter>,
    )
    const prepare = await screen.findByRole('link', { name: 'Özet hazırla' })
    expect(prepare).toHaveAttribute('href', '/client/summaries?appointment=a1')
    expect(screen.getByRole('link', { name: 'Not yaz' })).toHaveAttribute('href', '/client/after-session')
    expect(screen.getByText('Dünkü seansın için kısa bir not?')).toBeInTheDocument()
  })

  it('renders nothing without reminders or when the request fails', async () => {
    mockFetch({ 'GET /reminders': { body: [] } })
    const { container } = render(
      <MemoryRouter>
        <ReminderStrip />
      </MemoryRouter>,
    )
    await new Promise((res) => setTimeout(res, 20))
    expect(container).toBeEmptyDOMElement()
  })
})

describe('Hesabım', () => {
  it('downloads the export as a JSON file', async () => {
    const { calls } = mockFetch({ 'GET /account/export': { body: { profile: { email: 'ayse@x.test' }, entries: [] } } })
    const createUrl = vi.fn(() => 'blob:x')
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: vi.fn() }))
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    render(<Account />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Verimi indir' }))
    await vi.waitFor(() => expect(click).toHaveBeenCalled())
    expect(calls.map((c) => c.key)).toEqual(['GET /account/export'])
    expect(createUrl).toHaveBeenCalled()
    click.mockRestore()
  })

  it('requires the password and the typed word before deleting, then ends the session', async () => {
    const { calls } = mockFetch({ 'DELETE /account': { status: 204 } })
    render(<Account />)
    const u = userEvent.setup()
    await u.click(screen.getByRole('button', { name: 'Hesabımı silmek istiyorum' }))
    const submit = screen.getByRole('button', { name: 'Hesabımı kalıcı olarak sil' })
    expect(submit).toBeDisabled()
    await u.type(screen.getByLabelText('Parolan'), 'secret-password-1')
    await u.type(screen.getByLabelText(/Onaylamak için/), 'sil')
    expect(submit).toBeDisabled()
    await u.clear(screen.getByLabelText(/Onaylamak için/))
    await u.type(screen.getByLabelText(/Onaylamak için/), 'SİL')
    expect(submit).toBeEnabled()
    await u.click(submit)
    await vi.waitFor(() => expect(logout).toHaveBeenCalled())
    const del = calls.find((c) => c.key === 'DELETE /account')!
    expect(JSON.parse(String(del.init.body))).toEqual({ password: 'secret-password-1', confirmation: 'SİL' })
  })

  it('keeps the session and shows the error when the password is wrong', async () => {
    mockFetch({ 'DELETE /account': { status: 403, body: { detail: 'Password is incorrect' } } })
    render(<Account />)
    const u = userEvent.setup()
    await u.click(screen.getByRole('button', { name: 'Hesabımı silmek istiyorum' }))
    await u.type(screen.getByLabelText('Parolan'), 'wrong')
    await u.type(screen.getByLabelText(/Onaylamak için/), 'SİL')
    await u.click(screen.getByRole('button', { name: 'Hesabımı kalıcı olarak sil' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('yetkin yok')
    expect(logout).not.toHaveBeenCalled()
  })
})
