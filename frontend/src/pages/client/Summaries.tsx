import { useCallback, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { appointmentsApi, summariesApi } from '../../api/endpoints'
import type { SummaryJob, SummaryStatus } from '../../api/types'
import { Alert, Badge, Button, Card, Empty, formatDate, formatDateTime, PageHeader, SelectField, Spinner, TextField } from '../../components/ui'
import { useLoad } from '../../hooks/useLoad'
import { JobProgress } from './JobProgress'

export const STATUS_LABEL: Record<SummaryStatus, string> = {
  draft: 'Taslak',
  approved: 'Onaylandı',
  shared: 'Paylaşıldı',
  revoked: 'Paylaşım geri alındı',
}
export const STATUS_TONE: Record<SummaryStatus, 'amber' | 'indigo' | 'green' | 'slate'> = {
  draft: 'amber',
  approved: 'indigo',
  shared: 'green',
  revoked: 'slate',
}

const iso = (d: Date) => d.toISOString().slice(0, 10)

function GeneratePanel({ onFinished, initialAppointmentId = '' }: { onFinished: () => void; initialAppointmentId?: string }) {
  const today = new Date()
  const [start, setStart] = useState(iso(new Date(today.getTime() - 14 * 86400000)))
  const [end, setEnd] = useState(iso(today))
  const [appointmentId, setAppointmentId] = useState(initialAppointmentId)
  // Optional: the appointments to prepare for. A failed load just leaves the dates-only form.
  const { data: appointments } = useLoad(useCallback(() => appointmentsApi.list(), []))
  const [job, setJob] = useState<SummaryJob | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // One key per attempt: a double click or retry of the same request returns the same job.
  const [key, setKey] = useState(() => crypto.randomUUID())

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      setJob(
        await summariesApi.generate(appointmentId ? { appointment_id: appointmentId } : { period_start: start, period_end: end }, key),
      )
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  function reset() {
    setJob(null)
    setKey(crypto.randomUUID())
    onFinished()
  }

  if (job) return <JobProgress initial={job} onReset={reset} />

  return (
    <form onSubmit={submit} className="space-y-4" aria-label="Özet oluştur">
      {error && <Alert>{error}</Alert>}
      {appointments && appointments.length > 0 && (
        <SelectField label="Hangi randevu için? (isteğe bağlı)" value={appointmentId} onChange={(e) => setAppointmentId(e.target.value)}>
          <option value="">Randevu seçme, tarih aralığı gireceğim</option>
          {appointments.map((a) => (
            <option key={a.id} value={a.id}>
              {formatDateTime(a.scheduled_at)}
            </option>
          ))}
        </SelectField>
      )}
      {appointmentId ? (
        <p className="text-sm text-slate-600">Dönem, bir önceki randevundan seçtiğin randevuya kadar otomatik belirlenir.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Başlangıç tarihi" type="date" required value={start} max={end} onChange={(e) => setStart(e.target.value)} />
          <TextField label="Bitiş tarihi" type="date" required value={end} min={start} onChange={(e) => setEnd(e.target.value)} />
        </div>
      )}
      <p className="text-xs text-slate-500">En fazla 92 günlük bir aralık seçebilirsin. Özet yalnızca sana görünen bir taslak olarak oluşturulur.</p>
      <Button type="submit" disabled={busy}>
        {busy ? 'Gönderiliyor…' : 'Özet taslağı oluştur'}
      </Button>
    </form>
  )
}

export function Summaries() {
  // A reminder links here with ?appointment=<id>: the generate form opens with it selected.
  const preselected = useSearchParams()[0].get('appointment') ?? ''
  const [creating, setCreating] = useState(preselected !== '')
  const load = useCallback(() => summariesApi.list(), [])
  const { data, error, loading, reload } = useLoad(load)

  return (
    <div>
      <PageHeader title="Özetlerim" actions={<Button onClick={() => setCreating((c) => !c)}>{creating ? 'Kapat' : 'Yeni özet'}</Button>} />
      {creating && (
        <Card className="mb-5">
          <GeneratePanel onFinished={reload} initialAppointmentId={preselected} />
        </Card>
      )}
      {error && <Alert>{error}</Alert>}
      {loading ? (
        <Spinner />
      ) : data && data.length === 0 ? (
        <Empty>Henüz özet yok.</Empty>
      ) : (
        <ul className="space-y-3">
          {data?.map((s) => (
            <li key={s.id}>
              <Card>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Link to={`/client/summaries/${s.id}`} className="font-medium text-indigo-700 hover:underline">
                    {s.title}
                  </Link>
                  <Badge tone={STATUS_TONE[s.status]}>{STATUS_LABEL[s.status]}</Badge>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  {formatDate(s.period_start)} – {formatDate(s.period_end)}
                </p>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
