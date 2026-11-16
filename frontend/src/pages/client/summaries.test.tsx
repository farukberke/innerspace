import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { tokens } from '../../api/client'
import type { Summary, SummaryJob } from '../../api/types'
import { CrisisScreen } from '../../components/CrisisScreen'
import { mockFetch } from '../../test/mockFetch'
import { AfterSession } from './AfterSession'
import { JobProgress } from './JobProgress'
import { SummaryDetail } from './SummaryDetail'

const job = (over: Partial<SummaryJob>): SummaryJob => ({
  id: 'j1',
  status: 'queued',
  period_start: '2026-11-01',
  period_end: '2026-11-14',
  summary_id: null,
  error_code: null,
  attempts: 0,
  created_at: '2026-11-15T10:00:00Z',
  updated_at: '2026-11-15T10:00:00Z',
  crisis: null,
  ...over,
})

const CRISIS = {
  crisis: true,
  message: 'Sabit kriz mesajı. 112 ye ulaşabilirsin.',
  resources: [{ name: 'Acil Çağrı Merkezi', contact: '112' }],
}

afterEach(() => {
  tokens.clear()
  vi.unstubAllGlobals()
})

function renderJob(initial: SummaryJob) {
  return render(
    <MemoryRouter>
      <JobProgress initial={initial} intervalMs={10} onReset={() => {}} />
    </MemoryRouter>,
  )
}

describe('job polling', () => {
  it('polls until succeeded and links to the draft', async () => {
    let n = 0
    mockFetch({
      'GET /summaries/jobs/j1': () => {
        n += 1
        return { body: n < 2 ? job({ status: 'running' }) : job({ status: 'succeeded', summary_id: 's1' }) }
      },
    })
    renderJob(job({}))
    expect(screen.getByRole('status')).toHaveTextContent('hazırlanıyor')
    const link = await screen.findByRole('link', { name: 'Taslağı aç' })
    expect(link).toHaveAttribute('href', '/client/summaries/s1')
    expect(n).toBe(2)
  })

  it('shows the fixed crisis screen when the job ends in crisis', async () => {
    mockFetch({ 'GET /summaries/jobs/j1': { body: job({ status: 'crisis', crisis: CRISIS }) } })
    renderJob(job({ status: 'running' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Sabit kriz mesajı')
    expect(screen.getByText('112')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Taslağı aç' })).not.toBeInTheDocument()
  })

  it('shows a failure message and stops polling', async () => {
    const { fn } = mockFetch({ 'GET /summaries/jobs/j1': { body: job({ status: 'failed', error_code: 'no_entries' }) } })
    renderJob(job({ status: 'running' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('kayıt bulunamadı')
    const calls = fn.mock.calls.length
    await new Promise((r) => setTimeout(r, 60))
    expect(fn.mock.calls.length).toBe(calls)
  })

  it('renders a terminal initial job without polling', () => {
    const { fn } = mockFetch({})
    renderJob(job({ status: 'crisis', crisis: CRISIS }))
    expect(screen.getByRole('alert')).toHaveTextContent('Sabit kriz mesajı')
    expect(fn).not.toHaveBeenCalled()
  })
})

describe('crisis screen', () => {
  it('shows the backend message and resources', () => {
    render(<CrisisScreen crisis={CRISIS} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Sabit kriz mesajı')
    expect(screen.getByText('Acil Çağrı Merkezi')).toBeInTheDocument()
  })

  it('is shown for an after-session note answered with the crisis response', async () => {
    mockFetch({ 'GET /after-session-notes': { body: [] }, 'POST /after-session-notes': { body: CRISIS } })
    render(<AfterSession />)
    const u = userEvent.setup()
    await u.type(await screen.findByLabelText(/Seans nasıldı/), 'bir not')
    await u.click(screen.getByRole('button', { name: /Notu düzenle/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Sabit kriz mesajı')
  })
})

const draft: Summary = {
  id: 's1',
  client_id: 'c1',
  title: 'Özet',
  body: 'x',
  status: 'draft',
  period_start: '2026-11-01',
  period_end: '2026-11-14',
  statements: [{ id: 'st1', section: 'Genel', text: 'Uykum bozuldu.', source_entry_ids: ['e1'] }],
  approved_at: null,
  shared_at: null,
  created_at: '2026-11-15T10:00:00Z',
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={['/client/summaries/s1']}>
      <Routes>
        <Route path="/client/summaries/:id" element={<SummaryDetail />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('summary detail', () => {
  it('shows the guardrail 422 message when an edit is rejected', async () => {
    mockFetch({
      'GET /summaries/s1': { body: draft },
      'PATCH /summaries/s1': { status: 422, body: { detail: 'Statement contains treatment advice' } },
    })
    renderDetail()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: 'Düzenle' }))
    const box = screen.getByLabelText(/ifade 1/)
    await u.clear(box)
    await u.type(box, 'İlacı bırakmalısın')
    await u.click(screen.getByRole('button', { name: 'Değişiklikleri kaydet' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Statement contains treatment advice')
  })

  it('approves then shares, and can revoke', async () => {
    mockFetch({
      'GET /summaries/s1': { body: draft },
      'POST /summaries/s1/approve': { body: { ...draft, status: 'approved' } },
      'POST /summaries/s1/share': { body: { ...draft, status: 'shared' } },
      'POST /summaries/s1/unshare': { body: { ...draft, status: 'revoked' } },
    })
    renderDetail()
    const u = userEvent.setup()
    await u.click(await screen.findByRole('button', { name: 'Onayla' }))
    await u.click(await screen.findByRole('button', { name: 'Uzmanımla paylaş' }))
    await u.click(await screen.findByRole('button', { name: 'Paylaşımı geri al' }))
    expect(await screen.findByText('Paylaşım geri alındı')).toBeInTheDocument()
  })

  it('does not offer sharing for a draft', async () => {
    mockFetch({ 'GET /summaries/s1': { body: draft } })
    renderDetail()
    await screen.findByRole('button', { name: 'Onayla' })
    expect(screen.queryByRole('button', { name: 'Uzmanımla paylaş' })).not.toBeInTheDocument()
  })
})
