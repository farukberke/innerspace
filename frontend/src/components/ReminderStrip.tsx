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
    <ul aria-label="Hatırlatmalar" className="mb-4 space-y-2">
      {data.map((r) => {
        const action = ACTION[r.kind](r)
        return (
          <li
            key={`${r.kind}-${r.appointment_id}`}
            className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-indigo-50 px-4 py-3 text-sm text-indigo-900"
          >
            <span>{r.message}</span>
            <Link to={action.to} className="font-medium text-indigo-700 underline-offset-2 hover:underline">
              {action.label}
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
