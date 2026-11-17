import { useCallback } from 'react'
import { Link } from 'react-router-dom'
import { remindersApi } from '../api/endpoints'
import type { Reminder } from '../api/types'
import { useLoad } from '../hooks/useLoad'

const ACTION: Record<Reminder['kind'], (r: Reminder) => { to: string; label: string }> = {
  prepare_summary: (r) => ({ to: `/client/summaries?appointment=${r.appointment_id}`, label: 'Özet hazırla' }),
  after_session_note: () => ({ to: '/client/after-session', label: 'Not yaz' }),
}

/** Calm, optional nudges computed by the backend. Nothing is shown when there are none or the
 *  request fails: a reminder must never get in the way. */
export function ReminderStrip() {
  const { data } = useLoad(useCallback(() => remindersApi.list(), []))
  if (!data || data.length === 0) return null
  return (
    <ul aria-label="Hatırlatmalar" className="mb-5 space-y-2">
      {data.map((r) => {
        const action = ACTION[r.kind](r)
        return (
          <li
            key={`${r.kind}-${r.appointment_id}`}
            className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-soft-lg bg-warn-100 px-4 py-3 text-base text-warn-900"
          >
            <span className="flex items-center gap-3">
              <span aria-hidden className="h-2.5 w-2.5 shrink-0 rounded-full bg-warn-300" />
              {r.message}
            </span>
            <Link to={action.to} className="inline-flex min-h-11 items-center font-bold text-warn-900 underline underline-offset-4">
              {action.label}
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
