import { useCallback, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { appointmentsApi, summariesApi } from '../../api/endpoints'
import type { SummaryJob, SummaryStatus } from '../../api/types'
import { ArrowIcon, PlusIcon } from '../../components/icons'
import { Alert, Badge, Button, Card, Empty, formatDate, formatDateTime, PageHeader, SelectField, Spinner, TextField } from '../../components/ui'
import { useLoad } from '../../hooks/useLoad'
import { JobProgress } from './JobProgress'

export const STATUS_LABEL: Record<SummaryStatus, string> = {
  draft: 'Taslak',
  approved: 'Onaylandı',
  shared: 'Paylaşıldı',
  revoked: 'Paylaşım geri alındı',
}
export const STATUS_TONE: Record<SummaryStatus, 'amber' | 'brand' | 'green' | 'slate'> = {
  draft: 'amber',
  approved: 'brand',
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
        <p className="text-sm text-ink-2">Dönem, bir önceki randevundan seçtiğin randevuya kadar otomatik belirlenir.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Başlangıç tarihi" type="date" required value={start} max={end} onChange={(e) => setStart(e.target.value)} />
          <TextField label="Bitiş tarihi" type="date" required value={end} min={start} onChange={(e) => setEnd(e.target.value)} />
        </div>
      )}
      <p className="text-xs text-muted">En fazla 92 günlük bir aralık seçebilirsin. Özet yalnızca sana görünen bir taslak olarak oluşturulur.</p>
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
      <PageHeader
        title="Özetlerim"
        lede="Seçtiğin dönemin kayıtlarından, kendi cümlelerinle. Sen onaylayıp paylaşmadan kimse görmez."
        actions={
          <Button onClick={() => setCreating((c) => !c)} variant={creating ? 'secondary' : 'primary'}>
            {creating ? 'Kapat' : (
              <>
                <PlusIcon /> Yeni özet
              </>
            )}
          </Button>
        }
      />
      {creating && (
        <Card className="mb-6">
          <GeneratePanel onFinished={reload} initialAppointmentId={preselected} />
        </Card>
      )}
      {error && <Alert>{error}</Alert>}
      {loading ? (
        <Spinner />
      ) : data && data.length === 0 ? (
        <Empty
          title="Henüz özet yok"
          action={
            creating ? null : (
              <Button onClick={() => setCreating(true)}>
                <PlusIcon /> İlk özetini hazırla
              </Button>
            )
          }
        >
          Randevundan önce bir dönem seç; AI yalnızca o dönemdeki kayıtlarını toparlar, her cümlenin hangi kayıtlara dayandığını gösterir.
        </Empty>
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-soft-lg border border-line bg-surface">
          {data?.map((s) => (
            <li key={s.id}>
              <Link to={`/client/summaries/${s.id}`} className="group flex items-center gap-4 px-4 py-4 hover:bg-brand-50 sm:px-5">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="text-lg font-bold text-ink group-hover:underline group-hover:underline-offset-4">{s.title}</span>
                    <Badge tone={STATUS_TONE[s.status]}>{STATUS_LABEL[s.status]}</Badge>
                  </div>
                  <p className="num mt-1 text-[0.9375rem] text-muted">
                    {formatDate(s.period_start)} – {formatDate(s.period_end)} · {s.statements.length} ifade
                  </p>
                </div>
                <ArrowIcon className="shrink-0 text-brand-600" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
