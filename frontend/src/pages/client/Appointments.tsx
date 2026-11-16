import { useCallback, useState } from 'react'
import { appointmentsApi } from '../../api/endpoints'
import type { Appointment } from '../../api/types'
import { APPOINTMENT_KIND_LABEL } from '../../components/AppointmentForm'
import { Alert, Card, Empty, formatDateTime, PageHeader, Spinner } from '../../components/ui'
import { useLoad } from '../../hooks/useLoad'

function list(items: Appointment[]) {
  return (
    <ul className="space-y-3">
      {items.map((a) => (
        <li key={a.id}>
          <Card>
            <p className="font-medium text-ink">{formatDateTime(a.scheduled_at)}</p>
            <p className="mt-1 text-sm text-ink-2">
              {APPOINTMENT_KIND_LABEL[a.kind]}
              {a.clinician_name ? ` · ${a.clinician_name}` : ''}
            </p>
          </Card>
        </li>
      ))}
    </ul>
  )
}

/** Read-only: appointments are opened, changed and cancelled by the assigned clinician. */
export function Appointments() {
  const load = useCallback(() => appointmentsApi.list(), [])
  const { data, error, loading } = useLoad(load)
  const [now] = useState(() => Date.now())

  const upcoming = (data ?? []).filter((a) => new Date(a.scheduled_at).getTime() >= now).reverse()
  const past = (data ?? []).filter((a) => new Date(a.scheduled_at).getTime() < now)

  return (
    <div>
      <PageHeader title="Randevularım" />
      <p className="mb-4 text-sm text-ink-2">Uzmanının senin için açtığı randevular burada görünür. Değişiklik için uzmanınla konuş.</p>
      {error && <Alert>{error}</Alert>}
      {loading ? (
        <Spinner />
      ) : data && data.length === 0 ? (
        <Empty>Henüz randevu yok.</Empty>
      ) : (
        <div className="space-y-6">
          <section aria-labelledby="upcoming-title">
            <h2 id="upcoming-title" className="mb-2 text-base font-semibold text-ink-2">
              Yaklaşan
            </h2>
            {upcoming.length ? list(upcoming) : <Empty>Yaklaşan randevu yok.</Empty>}
          </section>
          {past.length > 0 && (
            <section aria-labelledby="past-title">
              <h2 id="past-title" className="mb-2 text-base font-semibold text-ink-2">
                Geçmiş
              </h2>
              {list(past)}
            </section>
          )}
        </div>
      )}
    </div>
  )
}
