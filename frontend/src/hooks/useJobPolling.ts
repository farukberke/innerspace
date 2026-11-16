import { useEffect, useState } from 'react'
import { errorMessage } from '../api/client'
import { summariesApi } from '../api/endpoints'
import type { SummaryJob } from '../api/types'

export const TERMINAL_STATUSES = ['succeeded', 'failed', 'crisis'] as const

export function isTerminal(job: SummaryJob | null): boolean {
  return job !== null && (TERMINAL_STATUSES as readonly string[]).includes(job.status)
}

/** Polls a summary job until it reaches succeeded / failed / crisis. */
export function useJobPolling(initial: SummaryJob | null, intervalMs = 2000) {
  const [job, setJob] = useState<SummaryJob | null>(initial)
  const [error, setError] = useState<string | null>(null)
  const jobId = initial?.id ?? null

  useEffect(() => {
    if (!jobId) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const tick = async () => {
      try {
        const next = await summariesApi.job(jobId)
        if (cancelled) return
        setJob(next)
        setError(null)
        if (isTerminal(next)) return
      } catch (err) {
        if (cancelled) return
        setError(errorMessage(err))
      }
      timer = setTimeout(tick, intervalMs)
    }
    timer = setTimeout(tick, intervalMs)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [jobId, intervalMs])

  return { job: job?.id === jobId ? job : initial, error }
}
