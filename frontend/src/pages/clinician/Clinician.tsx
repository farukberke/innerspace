import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { clinicianApi } from '../../api/endpoints'
import { AiDisclaimer } from '../../components/AiDisclaimer'
import type { ClientRead } from '../../api/types'
import { ArrowIcon } from '../../components/icons'
import { SummaryReading } from '../../components/SummaryReading'
import { Alert, BackLink, Button, Empty, formatDate, formatDateTime, formatShortDate, PageHeader, relativeDay, Spinner } from '../../components/ui'
import { useLoad } from '../../hooks/useLoad'
import { InviteForm } from '../InviteForm'

/** Clients with something new first, then by the next appointment, then by name. */
export function sortClients(items: ClientRead[]): ClientRead[] {
  const t = (iso: string | null) => (iso ? new Date(iso).getTime() : Number.POSITIVE_INFINITY)
  return [...items].sort(
    (a, b) =>
      Number(b.new_summaries > 0) - Number(a.new_summaries > 0) ||
      t(a.next_appointment_at) - t(b.next_appointment_at) ||
      a.display_name.localeCompare(b.display_name, 'tr'),
  )
}

function NewDot({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-2.5 py-0.5 text-[0.8125rem] font-bold text-brand-800">
      <span aria-hidden className="h-2 w-2 rounded-full bg-brand-600" />
      {label}
    </span>
  )
}

export function ClinicianClients() {
  const [inviting, setInviting] = useState(false)
  const load = useCallback(() => clinicianApi.clients(), [])
  const { data, error, loading } = useLoad(load)
  // Newest unopened summary per client, for a direct "open" action (metadata only).
  const shared = useLoad(useCallback(() => clinicianApi.summaries(), []))
  const newest = new Map<string, string>()
  for (const s of shared.data ?? []) if (s.is_new && !newest.has(s.client_id)) newest.set(s.client_id, s.id)
  const clients = data ? sortClients(data) : []
  const newTotal = clients.reduce((n, c) => n + c.new_summaries, 0)
  return (
    <div>
      <PageHeader
        title="Danışanlarım"
        lede={
          data && data.length > 0
            ? newTotal > 0
              ? `${newTotal} yeni paylaşılan özet var. Yalnızca danışanların seninle paylaştıklarını görürsün.`
              : 'Yeni paylaşım yok. Yalnızca danışanların seninle paylaştıklarını görürsün.'
            : undefined
        }
        actions={
          <Button onClick={() => setInviting((i) => !i)} variant={inviting ? 'secondary' : 'primary'}>
            {inviting ? 'Kapat' : 'Danışan davet et'}
          </Button>
        }
      />
      {inviting && (
        <div className="mb-6">
          <InviteForm roles={['client']} />
        </div>
      )}
      {error && <Alert>{error}</Alert>}
      {loading ? (
        <Spinner />
      ) : clients.length === 0 ? (
        <Empty title="Sana atanmış danışan yok">
          Klinik yöneticin seni bir danışana atadığında ya da davet ettiğin bir danışan hesabını açtığında burada görünür.
        </Empty>
      ) : (
        <div className="overflow-hidden rounded-soft-lg border border-line bg-surface">
          <div className="hidden grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)] gap-4 border-b border-ink px-5 py-2.5 text-[0.8125rem] font-bold text-muted md:grid">
            <span>Danışan</span>
            <span>Son paylaşım</span>
            <span>Sonraki randevu</span>
          </div>
          <ul className="divide-y divide-line">
            {clients.map((c) => (
              <li
                key={c.id}
                className="grid gap-x-4 gap-y-1 px-4 py-4 sm:px-5 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)] md:items-center"
              >
                <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <Link to={`/clinician/clients/${c.id}`} className="inline-flex min-h-11 items-center text-lg font-bold text-ink underline decoration-line-strong decoration-1 underline-offset-4 hover:decoration-ink">
                    {c.display_name}
                  </Link>
                  {c.new_summaries > 0 && <NewDot label={c.new_summaries === 1 ? 'Yeni özet' : `${c.new_summaries} yeni özet`} />}
                </span>
                <span className="num flex flex-wrap items-center gap-x-3 text-[0.9375rem] text-ink-2">
                  <span>
                    <span className="text-muted md:hidden">Son paylaşım: </span>
                    {c.last_shared_at ? `${formatShortDate(c.last_shared_at)} · ${relativeDay(c.last_shared_at)}` : 'Henüz paylaşım yok'}
                  </span>
                  {newest.has(c.id) && (
                    <Link to={`/clinician/summaries/${newest.get(c.id)}`} className="link inline-flex min-h-11 items-center">
                      Yeni özeti aç
                    </Link>
                  )}
                </span>
                <span className="num text-[0.9375rem] text-ink-2">
                  <span className="text-muted md:hidden">Sonraki randevu: </span>
                  {c.next_appointment_at ? formatDateTime(c.next_appointment_at) : 'Planlı randevu yok'}
                </span>
              </li>
            ))}
          </ul>
        </div>
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
      <PageHeader
        title="Paylaşılan özetler"
        lede="Danışanların onaylayıp seninle paylaştığı özetler, en yeni paylaşım üstte. Danışan paylaşımı geri alabilir."
      />
      {summaries.error && <Alert>{summaries.error}</Alert>}
      {summaries.loading ? (
        <Spinner />
      ) : summaries.data && summaries.data.length === 0 ? (
        <Empty title="Henüz paylaşılan özet yok">
          Danışanların randevudan önce kendi kayıtlarından bir özet hazırlayıp onayladığında ve seninle paylaştığında burada görünür.
        </Empty>
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-soft-lg border border-line bg-surface">
          {summaries.data?.map((s) => (
            <li key={s.id}>
              <Link to={`/clinician/summaries/${s.id}`} className="group flex items-center gap-4 px-4 py-4 hover:bg-brand-50 sm:px-5">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="text-lg font-bold text-ink group-hover:underline group-hover:underline-offset-4">
                      {names.get(s.client_id) ?? 'Danışan'}
                    </span>
                    <span className="text-ink-2">{s.title}</span>
                    {s.is_new && <NewDot label="Yeni" />}
                  </div>
                  <p className="num mt-1 text-[0.9375rem] text-muted">
                    {formatDate(s.period_start)} – {formatDate(s.period_end)} · paylaşım {s.shared_at ? formatDateTime(s.shared_at) : '—'}
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
  const sections = parseSummaryBody(data.body).map((sec, i) => ({
    heading: sec.heading,
    items: sec.items.map((text, j) => ({ key: `${i}-${j}`, text })),
  }))
  return (
    <div>
      <BackLink to="/clinician/summaries">Paylaşılan özetler</BackLink>
      <header className="mb-8 border-b border-line pb-6">
        <h1 className="text-[2rem] leading-[1.05] sm:text-[2.75rem]">{data.title}</h1>
        <p className="num mt-3 text-base text-ink-2">
          {formatDate(data.period_start)} – {formatDate(data.period_end)}
          {data.shared_at && <span className="text-muted"> · paylaşım {formatDateTime(data.shared_at)}</span>}
        </p>
      </header>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-12">
        <div className="min-w-0">
          <SummaryReading sections={sections} />
          {data.topics.length > 0 && (
            <section aria-labelledby="topics-title" className="mt-10 max-w-[66ch] rounded-soft-lg bg-brand-600 p-5 text-white sm:p-6">
              <h2 id="topics-title" className="text-[1.0625rem] font-extrabold">
                Danışanın konuşmak istediği konular
              </h2>
              <ul className="mt-3 list-disc space-y-1.5 pl-5 text-[1.0625rem] leading-relaxed marker:text-brand-200">
                {data.topics.map((t, i) => (
                  <li key={i} className="break-words">
                    {t}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
        <aside className="lg:sticky lg:top-8 lg:self-start">
          <div className="rounded-soft-lg border border-line bg-surface p-5">
            <h2 className="text-lg font-extrabold">Bu özet hakkında</h2>
            <p className="mt-2 text-[0.9375rem] leading-relaxed text-ink-2">
              Danışan bu özeti onaylayıp seninle paylaştı; paylaşımı istediği an geri alabilir. Ham kayıtlar yalnızca danışanda kalır.
            </p>
            <AiDisclaimer audience="clinician" />
          </div>
        </aside>
      </div>
    </div>
  )
}
