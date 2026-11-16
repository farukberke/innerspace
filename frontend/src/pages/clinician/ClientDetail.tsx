import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, errorMessage } from '../../api/client'
import { clinicianApi } from '../../api/endpoints'
import type { Appointment, AppointmentInput, PlanContent } from '../../api/types'
import { AppointmentForm, APPOINTMENT_KIND_LABEL } from '../../components/AppointmentForm'
import { Alert, Button, Card, Empty, formatDateTime, PageHeader, Spinner } from '../../components/ui'
import { useLoad } from '../../hooks/useLoad'
import { telHref } from '../client/Moment'

function Items({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null
  return (
    <div className="mt-4">
      <h3 className="text-base font-semibold text-ink-2">{title}</h3>
      <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-ink">
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
          <h3 className="text-base font-semibold text-ink-2">Kendine not</h3>
          <p className="mt-1 whitespace-pre-wrap break-words text-sm text-ink">{plan.self_note}</p>
        </div>
      )}
      {plan.contacts.length > 0 && (
        <div className="mt-4">
          <h3 className="text-base font-semibold text-ink-2">Aranacak kişiler</h3>
          <ul className="mt-1 space-y-1 text-sm text-ink">
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
  if (!data) return <Empty>Danışan planını seninle paylaşmadı.</Empty>
  return (
    <div>
      <p className="text-xs text-muted">Salt okunur · Paylaşım: {formatDateTime(data.shared_at)} · Danışan paylaşımı geri alabilir.</p>
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

  const notFound = error !== null && !data
  return (
    <div className="space-y-6">
      <p className="text-sm">
        <Link to="/clinician/clients" className="link inline-flex min-h-11 items-center">
          ← Danışanlarım
        </Link>
      </p>
      <PageHeader title={name} actions={!form && <Button onClick={() => setForm('new')}>Randevu oluştur</Button>} />
      {form && (
        <Card>
          <AppointmentForm appointment={form === 'new' ? undefined : form} onSubmit={save} onCancel={() => setForm(null)} />
        </Card>
      )}
      <section aria-labelledby="appts-title">
        <h2 id="appts-title" className="mb-2 text-lg font-semibold text-ink">
          Randevular
        </h2>
        {(notFound || actionError) && <Alert>{actionError ?? error}</Alert>}
        {loading ? (
          <Spinner />
        ) : data && data.length === 0 ? (
          <Empty>Henüz randevu yok.</Empty>
        ) : (
          <ul className="space-y-3">
            {data?.map((a) => (
              <li key={a.id}>
                <Card>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="font-medium">{formatDateTime(a.scheduled_at)}</p>
                      <p className="mt-1 text-sm text-ink-2">
                        {APPOINTMENT_KIND_LABEL[a.kind]}
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 flex gap-2">
                    <Button variant="secondary" onClick={() => setForm(a)}>
                      Değiştir
                    </Button>
                    <Button variant="danger" onClick={() => cancel(a)}>
                      İptal et
                    </Button>
                  </div>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-labelledby="plan-title">
        <h2 id="plan-title" className="mb-2 text-lg font-semibold text-ink">
          Danışanın planı
        </h2>
        <Card>
          <ClientPlan clientId={id} />
        </Card>
      </section>
    </div>
  )
}
