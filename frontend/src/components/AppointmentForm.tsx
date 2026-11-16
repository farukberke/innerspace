import { useState, type FormEvent } from 'react'
import { errorMessage } from '../api/client'
import type { Appointment, AppointmentInput, AppointmentKind } from '../api/types'
import { toLocalInput } from '../pages/client/EntryForm'
import { Alert, Button, SelectField, TextField } from './ui'

export const APPOINTMENT_KIND_LABEL: Record<AppointmentKind, string> = {
  therapy: 'Terapi',
  psychiatry: 'Psikiyatri',
}

/** Create/edit form for the clinician (clients only view appointments). */
export function AppointmentForm({
  appointment,
  onSubmit,
  onCancel,
}: {
  appointment?: Appointment
  onSubmit: (body: AppointmentInput) => Promise<void>
  onCancel: () => void
}) {
  const [kind, setKind] = useState<AppointmentKind>(appointment?.kind ?? 'therapy')
  const [when, setWhen] = useState(appointment ? toLocalInput(appointment.scheduled_at) : '')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await onSubmit({ kind, scheduled_at: new Date(when).toISOString() })
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" aria-label={appointment ? 'Randevuyu düzenle' : 'Randevu ekle'}>
      {error && <Alert>{error}</Alert>}
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField label="Tür" value={kind} onChange={(e) => setKind(e.target.value as AppointmentKind)}>
          {(Object.keys(APPOINTMENT_KIND_LABEL) as AppointmentKind[]).map((k) => (
            <option key={k} value={k}>
              {APPOINTMENT_KIND_LABEL[k]}
            </option>
          ))}
        </SelectField>
        <TextField label="Tarih ve saat" type="datetime-local" required value={when} onChange={(e) => setWhen(e.target.value)} />
      </div>
      <div className="flex gap-2">
        <Button type="submit" disabled={busy || !when}>
          {busy ? 'Kaydediliyor…' : 'Kaydet'}
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          Vazgeç
        </Button>
      </div>
    </form>
  )
}
