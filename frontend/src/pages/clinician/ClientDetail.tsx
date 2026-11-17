import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, errorMessage } from '../../api/client'
import { clinicianApi } from '../../api/endpoints'
import type { Appointment, AppointmentInput, PlanContent } from '../../api/types'
import { AppointmentForm, APPOINTMENT_KIND_LABEL } from '../../components/AppointmentForm'
import { ArrowIcon } from '../../components/icons'
import { Alert, BackLink, Button, Card, Empty, formatDate, formatDateTime, Spinner } from '../../components/ui'
import { useLoad } from '../../hooks/useLoad'
import { telHref } from '../client/Moment'

function Items({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null
  return (
    <div className="mt-4">
      <h3 className="text-base font-bold text-ink">{title}</h3>
      <ul className="mt-1 list-disc space-y-1 pl-5 text-base text-ink-2 marker:text-brand-600">
        {items.map((t, i) => (
          <li key={i} className="break-words">
            {t}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Read-only view of a plan the client has shared. */
export function SharedPlanView({ plan }: { plan: PlanContent }) {
  return (
    <div>
      <Items title="O an adımları" items={plan.moment_steps} />
      {plan.self_note && (
        <div className="mt-4">
          <h3 className="text-base font-bold text-ink">Kendine not</h3>
          <p className="mt-1 whitespace-pre-wrap break-words text-base text-ink-2">{plan.self_note}</p>
        </div>
      )}
      {plan.contacts.length > 0 && (
        <div className="mt-4">
          <h3 className="text-base font-bold text-ink">Aranacak kişiler</h3>
          <ul className="mt-1 space-y-1 text-base text-ink-2">
            {plan.contacts.map((c, i) => (
              <li key={i}>
                {c.name} ·{' '}
                <a href={telHref(c.phone)} className="link inline-flex min-h-11 items-center">
                  {c.phone}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
      <Items title="Uyarı işaretleri" items={plan.warning_signs} />
      <Items title="İşe yarayan başa çıkma yolları" items={plan.coping_strategies} />
      <Items title="Seansta konuşmak istedikleri" items={plan.talk_to_clinician} />
    </div>
  )
}

function ClientPlan({ clientId }: { clientId: string }) {
  // 404 is the normal "not shared" state (never shared, withdrawn, or no longer assigned).
  const load = useCallback(
    () =>
      clinicianApi.plan(clientId).catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) return null
        throw err
      }),
    [clientId],
  )
  const { data, error, loading } = useLoad(load)
  if (loading) return <Spinner />
  if (error) return <Alert>{error}</Alert>
  if (!data) return <Empty title="Plan paylaşılmadı.">Danışan Planım sayfasını seninle paylaştığında, salt okunur olarak burada görünür.</Empty>
  return (
    <div>
      <p className="num text-[0.875rem] text-muted">Salt okunur · Paylaşım: {formatDateTime(data.shared_at)} · Danışan paylaşımı geri alabilir.</p>
      <SharedPlanView plan={data} />
    </div>
  )
}

export function ClinicianClientDetail() {
  const { id = '' } = useParams()
  const clients = useLoad(useCallback(() => clinicianApi.clients(), []))
  const load = useCallback(() => clinicianApi.appointments(id), [id])
  const { data, error, loading, reload } = useLoad(load)
  const [form, setForm] = useState<'new' | Appointment | null>(null)
  const [now] = useState(() => Date.now())
  const [actionError, setActionError] = useState<string | null>(null)
  const name = clients.data?.find((c) => c.id === id)?.display_name ?? 'Danışan'

  async function save(body: AppointmentInput) {
    if (form && form !== 'new') await clinicianApi.updateAppointment(form.id, body)
    else await clinicianApi.createAppointment(id, body)
    setForm(null)
    reload()
  }

  async function cancel(a: Appointment) {
    if (!window.confirm('Bu randevu iptal edilsin mi?')) return
    setActionError(null)
    try {
      await clinicianApi.deleteAppointment(a.id)
      reload()
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }

  const upcoming = (data ?? []).filter((a) => new Date(a.scheduled_at).getTime() >= now).reverse()
  const past = (data ?? []).filter((a) => new Date(a.scheduled_at).getTime() < now)

  // Past appointments are history: only upcoming ones can be changed or cancelled.
  const list = (items: Appointment[], editable: boolean) => (
    <ul className="divide-y divide-line overflow-hidden rounded-soft-lg border border-line bg-surface">
      {items.map((a) => (
        <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3.5">
          <div>
            <p className="num font-bold">{formatDateTime(a.scheduled_at)}</p>
            <p className="text-[0.9375rem] text-ink-2">{APPOINTMENT_KIND_LABEL[a.kind]}</p>
          </div>
          {editable && (
            <div className="flex gap-1">
              <Button variant="ghost" onClick={() => setForm(a)}>
                Değiştir
              </Button>
              <Button variant="ghost" className="text-danger-700 hover:bg-danger-50" onClick={() => cancel(a)}>
                İptal et
              </Button>
            </div>
          )}
        </li>
      ))}
    </ul>
  )

  const notFound = error !== null && !data
  const client = clients.data?.find((c) => c.id === id)
  return (
    <div>
      <BackLink to="/clinician/clients">Danışanlarım</BackLink>
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b border-line pb-6">
        <div>
          <h1 className="text-[2rem] leading-[1.05] sm:text-[2.75rem]">{name}</h1>
          {client && (
            <p className="num mt-2 text-base text-ink-2">
              {client.last_shared_at ? `Son paylaşım ${formatDate(client.last_shared_at)}` : 'Henüz özet paylaşmadı'}
              {client.new_summaries > 0 && <span className="font-bold text-danger-700"> · {client.new_summaries} yeni özet</span>}
            </p>
          )}
        </div>
        {!form && <Button onClick={() => setForm('new')}>Randevu oluştur</Button>}
      </div>
      {form && (
        <Card className="mb-6">
          <AppointmentForm appointment={form === 'new' ? undefined : form} onSubmit={save} onCancel={() => setForm(null)} />
        </Card>
      )}
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <div className="space-y-10">
          <ClientSummaries clientId={id} />
          <section aria-labelledby="plan-title">
            <h2 id="plan-title" className="mb-3 text-xl font-extrabold">
              Danışanın planı
            </h2>
            <div className="rounded-soft-lg border border-line bg-surface p-5">
              <ClientPlan clientId={id} />
            </div>
          </section>
        </div>
        <section aria-labelledby="appts-title">
          <h2 id="appts-title" className="mb-3 text-xl font-extrabold">
            Randevular
          </h2>
          {(notFound || actionError) && <Alert>{actionError ?? error}</Alert>}
          {loading ? (
            <Spinner />
          ) : data && data.length === 0 ? (
            <Empty title="Henüz randevu yok.">“Randevu oluştur” ile ekleyebilirsin; danışan kendi takviminde görür ve bir gün önce hatırlatılır.</Empty>
          ) : (
            <div className="space-y-6">
              <div>
                <h3 className="mb-2 text-base font-bold text-ink-2">Yaklaşan</h3>
                {upcoming.length ? list(upcoming, true) : <Empty title="Yaklaşan randevu yok.">Geçmiş randevular aşağıda.</Empty>}
              </div>
              {past.length > 0 && (
                <div>
                  <h3 className="mb-2 text-base font-bold text-ink-2">Geçmiş</h3>
                  {list(past, false)}
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

/** Summaries this client shared with the clinician (metadata; the body opens on its own page). */
function ClientSummaries({ clientId }: { clientId: string }) {
  const { data, error, loading } = useLoad(useCallback(() => clinicianApi.summaries(), []))
  const mine = (data ?? []).filter((s) => s.client_id === clientId)
  return (
    <section aria-labelledby="shared-title">
      <h2 id="shared-title" className="mb-3 text-xl font-extrabold">
        Paylaştığı özetler
      </h2>
      {error && <Alert>{error}</Alert>}
      {loading ? (
        <Spinner />
      ) : mine.length === 0 ? (
        <Empty title="Paylaşılmış özet yok.">Danışan bir özeti onaylayıp seninle paylaştığında burada görünür.</Empty>
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-soft-lg border border-line bg-surface">
          {mine.map((s) => (
            <li key={s.id}>
              <Link to={`/clinician/summaries/${s.id}`} className="group flex items-center gap-4 px-4 py-3.5 hover:bg-brand-50">
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="font-bold group-hover:underline group-hover:underline-offset-4">{s.title}</span>
                    {s.is_new && (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-danger-50 px-2.5 py-0.5 text-[0.8125rem] font-bold text-danger-700">
                        <span aria-hidden className="h-2 w-2 rounded-full bg-attack" />
                        Yeni
                      </span>
                    )}
                  </p>
                  <p className="num text-[0.9375rem] text-muted">
                    {formatDate(s.period_start)} – {formatDate(s.period_end)}
                  </p>
                </div>
                <ArrowIcon className="shrink-0 text-brand-600" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
