import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { clinicianApi } from '../../api/endpoints'
import { AiDisclaimer } from '../../components/AiDisclaimer'
import { Alert, Button, Card, Empty, formatDate, formatDateTime, PageHeader, Spinner } from '../../components/ui'
import { useLoad } from '../../hooks/useLoad'
import { InviteForm } from '../InviteForm'

export function ClinicianClients() {
  const [inviting, setInviting] = useState(false)
  const load = useCallback(() => clinicianApi.clients(), [])
  const { data, error, loading } = useLoad(load)
  return (
    <div>
      <PageHeader title="Danışanlarım" actions={<Button onClick={() => setInviting((i) => !i)}>{inviting ? 'Kapat' : 'Danışan davet et'}</Button>} />
      {inviting && (
        <div className="mb-5">
          <InviteForm roles={['client']} />
        </div>
      )}
      {error && <Alert>{error}</Alert>}
      {loading ? (
        <Spinner />
      ) : data && data.length === 0 ? (
        <Empty>Sana atanmış danışan yok.</Empty>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {data?.map((c) => (
            <li key={c.id}>
              <Card>
                <Link to={`/clinician/clients/${c.id}`} className="link inline-flex min-h-11 items-center">
                  {c.display_name}
                </Link>
                <p className="mt-1 text-xs text-muted">
                  {c.next_appointment_at ? `Sonraki randevu: ${formatDateTime(c.next_appointment_at)}` : 'Planlı randevu yok'}
                </p>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function ClinicianSummaries() {
  const summaries = useLoad(useCallback(() => clinicianApi.summaries(), []))
  const clients = useLoad(useCallback(() => clinicianApi.clients(), []))
  const names = new Map(clients.data?.map((c) => [c.id, c.display_name]))
  return (
    <div>
      <PageHeader title="Paylaşılan özetler" />
      {summaries.error && <Alert>{summaries.error}</Alert>}
      {summaries.loading ? (
        <Spinner />
      ) : summaries.data && summaries.data.length === 0 ? (
        <Empty>Danışanların henüz seninle özet paylaşmadı.</Empty>
      ) : (
        <ul className="space-y-3">
          {summaries.data?.map((s) => (
            <li key={s.id}>
              <Card>
                <Link to={`/clinician/summaries/${s.id}`} className="link inline-flex min-h-11 items-center">
                  {s.title}
                </Link>
                <p className="mt-1 text-xs text-muted">
                  {names.get(s.client_id) ?? 'Danışan'} · {formatDate(s.period_start)} – {formatDate(s.period_end)} · Paylaşım:{' '}
                  {s.shared_at ? formatDateTime(s.shared_at) : '—'}
                </p>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

interface BodySection {
  heading: string | null
  items: string[]
}

/** The backend renders `body` as "## section" headings followed by "- statement" lines. */
export function parseSummaryBody(body: string): BodySection[] {
  const sections: BodySection[] = []
  for (const raw of body.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line) continue
    if (line.startsWith('## ')) {
      sections.push({ heading: line.slice(3).trim(), items: [] })
      continue
    }
    if (sections.length === 0) sections.push({ heading: null, items: [] })
    sections[sections.length - 1].items.push(line.startsWith('- ') ? line.slice(2) : line)
  }
  return sections
}

export function ClinicianSummaryDetail() {
  const { id = '' } = useParams()
  const { data, error, loading } = useLoad(useCallback(() => clinicianApi.summary(id), [id]))
  if (loading) return <Spinner />
  if (!data) return <Alert>{error ?? 'Özet yüklenemedi.'}</Alert>
  return (
    <div>
      <p className="mb-2 text-sm">
        <Link to="/clinician/summaries" className="link inline-flex min-h-11 items-center">
          ← Paylaşılan özetler
        </Link>
      </p>
      <PageHeader title={data.title} />
      <p className="mb-4 text-xs text-muted">
        {formatDate(data.period_start)} – {formatDate(data.period_end)}
      </p>
      <Card>
        <div className="space-y-4">
          {parseSummaryBody(data.body).map((sec, i) => (
            <section key={i}>
              {sec.heading && <h2 className="text-xs font-medium uppercase tracking-wide text-muted">{sec.heading}</h2>}
              <ul className="mt-1 space-y-1 text-sm leading-relaxed text-ink">
                {sec.items.map((t, j) => (
                  <li key={j} className="break-words">
                    {t}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </Card>
      <AiDisclaimer audience="clinician" />
      {data.topics.length > 0 && (
        <section aria-labelledby="topics-title" className="mt-4">
          <Card>
            <h2 id="topics-title" className="text-base font-semibold text-ink">
              Danışanın konuşmak istediği konular
            </h2>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink">
              {data.topics.map((t, i) => (
                <li key={i} className="break-words">
                  {t}
                </li>
              ))}
            </ul>
          </Card>
        </section>
      )}
      <p className="mt-3 text-xs text-muted">Bu özet danışan tarafından onaylanıp seninle paylaşıldı; danışan paylaşımı geri alabilir.</p>
    </div>
  )
}
