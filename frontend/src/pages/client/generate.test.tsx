import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { tokens } from '../../api/client'
import { mockFetch } from '../../test/mockFetch'
import { Summaries } from './Summaries'

afterEach(() => {
  tokens.clear()
  vi.unstubAllGlobals()
})

async function openForm() {
  render(
    <MemoryRouter>
      <Summaries />
    </MemoryRouter>,
  )
  const u = userEvent.setup()
  await u.click(await screen.findByRole('button', { name: 'Yeni özet' }))
  return u
}

describe('generate summary', () => {
  it('tells the user how long to wait on 429', async () => {
    mockFetch({
      'GET /summaries': { body: [] },
      'POST /summaries/generate': { status: 429, body: {}, headers: { 'Retry-After': '30' } },
    })
    const u = await openForm()
    await u.click(screen.getByRole('button', { name: 'Özet taslağı oluştur' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('30 saniye')
  })

  it('sends an Idempotency-Key and starts polling the job', async () => {
    const queued = {
      id: 'j9',
      status: 'queued',
      period_start: '2026-11-01',
      period_end: '2026-11-14',
      summary_id: null,
      error_code: null,
      attempts: 0,
      created_at: '',
      updated_at: '',
      crisis: null,
    }
    const { calls } = mockFetch({
      'GET /summaries': { body: [] },
      'POST /summaries/generate': { status: 202, body: queued },
      'GET /summaries/jobs/j9': { body: queued },
    })
    const u = await openForm()
    await u.click(screen.getByRole('button', { name: 'Özet taslağı oluştur' }))
    expect(await screen.findByText(/hazırlanıyor/)).toBeInTheDocument()
    const post = calls.find((c) => c.key === 'POST /summaries/generate')!
    expect((post.init.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy()
  })
})
