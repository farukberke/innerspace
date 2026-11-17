import { useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { appointmentsApi, summariesApi } from '../../api/endpoints'
import type { Appointment, Summary } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { ArrowIcon, PlusIcon } from '../../components/icons'
import { Mark, sectionMark } from '../../components/Mark'
import { ReminderStrip } from '../../components/ReminderStrip'
import { RhythmStrip } from '../../components/RhythmStrip'
import { Alert, Badge, calendarDaysUntil, formatDate, LinkButton, relativeDay, Spinner } from '../../components/ui'
import { useLoad } from '../../hooks/useLoad'
import { buildTrend, describeTrend, loadTrendEntries, TREND_DAYS, trendStats } from '../../lib/trend'
import { STATUS_LABEL, STATUS_TONE } from './Summaries'

const KIND_LABEL = { therapy: 'Terapi seansı', psychiatry: 'Psikiyatri randevusu' } as const

export function nextAppointment(items: Appointment[], now: Date): Appointment | null {
  const upcoming = items.filter((a) => new Date(a.scheduled_at).getTime() >= now.getTime())
  upcoming.sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at))
  return upcoming[0] ?? null
}

/** The newest summary, preferring the one currently shared. */
export function latestSummary(items: Summary[]): Summary | null {
  const byNewest = [...items].sort((a, b) => b.created_at.localeCompare(a.created_at))
  return byNewest.find((s) => s.status === 'shared') ?? byNewest[0] ?? null
}

function firstName(display: string): string {
  return display.split(/\s+/)[0] ?? display
}

function Rhythm({ now }: { now: Date }) {
  const { data, error, loading } = useLoad(useCallback(() => loadTrendEntries(now), [now]))
  const days = useMemo(() => buildTrend(data ?? [], now), [data, now])
  const stats = trendStats(days)
  return (
    <section aria-labelledby="rhythm-title" className="rounded-soft-lg border border-line bg-surface p-5 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="rhythm-title" className="text-lg font-extrabold">
          Son {TREND_DAYS} gün
        </h2>
        <Link to="/client/entries" className="link text-[0.9375rem]">
          Tüm kayıtlar
        </Link>
      </div>
      {error && <Alert>{error}</Alert>}
      {loading ? (
        <Spinner />
      ) : (
        <>
          <div className="mt-5">
            <RhythmStrip days={days} />
          </div>
          {stats.daysWithRecords === 0 ? (
            <p className="mt-5 border-t border-line pt-4 text-base text-ink-2">
              Bu dönemde uyku veya atak kaydın yok. Günlük kayda uyku saatini eklediğinde ya da bir atak kaydettiğinde burada görünür.
            </p>
          ) : (
            <p className="mt-5 max-w-[62ch] border-t border-line pt-4 text-base leading-relaxed text-ink-2">{describeTrend(stats).join(' ')}</p>
          )}
        </>
      )}
    </section>
  )
}

function NextAppointment({ appointment, summaries, now }: { appointment: Appointment | null; summaries: Summary[]; now: Date }) {
  if (!appointment) {
    return (
      <section aria-labelledby="appt-title" className="flex flex-col rounded-soft-lg bg-brand-600 p-6 text-white">
        <h2 id="appt-title" className="text-lg font-extrabold">
          Sıradaki randevu
        </h2>
        <p className="mt-4 text-[1.375rem] font-bold leading-snug">Planlı randevun yok.</p>
        <p className="mt-2 text-base text-brand-100">Randevular uzmanın tarafından eklenir. Eklendiğinde burada görünür ve bir gün önce hatırlatılır.</p>
        <Link to="/client/appointments" className="mt-auto pt-6 text-[0.9375rem] font-bold text-white underline underline-offset-4">
          Randevularım
        </Link>
      </section>
    )
  }
  const when = new Date(appointment.scheduled_at)
  const prepared = summaries.find((s) => s.appointment_id === appointment.id)
  const days = calendarDaysUntil(appointment.scheduled_at, now)
  return (
    <section aria-labelledby="appt-title" className="flex flex-col rounded-soft-lg bg-brand-600 p-5 text-white sm:p-6">
      <h2 id="appt-title" className="text-lg font-extrabold">
        Sıradaki randevu
      </h2>
      <p className="display num mt-3 text-[2.75rem] sm:mt-5 sm:text-[4.25rem]">
        {when.toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' })}
      </p>
      <p className="num mt-1 text-lg font-bold sm:mt-2 sm:text-xl">
        {when.toLocaleDateString('tr-TR', { weekday: 'long' })} {when.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}
      </p>
      <p className="mt-1 text-base text-brand-100">
        {KIND_LABEL[appointment.kind]}
        {appointment.clinician_name ? ` · ${appointment.clinician_name}` : ''} · {relativeDay(appointment.scheduled_at, now)}
      </p>
      <div className="mt-auto pt-5 sm:pt-7">
        {prepared ? (
          <>
            <p className="mb-3 text-base text-brand-50">
              Bu randevu için özetin var: <strong className="font-bold text-white">{STATUS_LABEL[prepared.status].toLocaleLowerCase('tr-TR')}</strong>.
            </p>
            <Link
              to={`/client/summaries/${prepared.id}`}
              className="btn inline-flex min-h-12 items-center gap-2 rounded-soft bg-white px-5 text-base font-extrabold text-brand-700 hover:bg-brand-50"
            >
              Özeti aç <ArrowIcon />
            </Link>
          </>
        ) : (
          <>
            <p className="mb-3 text-base text-brand-50">
              {days <= 2 ? 'Seansa az kaldı. Kayıtlarından kısa bir özet hazırlayabilirsin.' : 'Hazır olduğunda kayıtlarından kısa bir özet hazırlayabilirsin.'}
            </p>
            <Link
              to={`/client/summaries?appointment=${appointment.id}`}
              className="btn inline-flex min-h-12 items-center gap-2 rounded-soft bg-white px-5 text-base font-extrabold text-brand-700 hover:bg-brand-50"
            >
              Seansa hazırlan <ArrowIcon />
            </Link>
          </>
        )}
      </div>
    </section>
  )
}

function LastSummary({ summary }: { summary: Summary | null }) {
  return (
    <section aria-labelledby="last-summary-title" className="rounded-soft-lg border border-line bg-surface p-5 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="last-summary-title" className="text-lg font-extrabold">
          Son özet
        </h2>
        <Link to="/client/summaries" className="link text-[0.9375rem]">
          Özetlerim
        </Link>
      </div>
      {!summary ? (
        <p className="mt-3 text-base text-ink-2">
          Henüz bir özetin yok. Randevundan önce, seçtiğin dönemin kayıtlarından tek sayfalık bir özet hazırlayabilirsin; sen onaylamadan kimse görmez.
        </p>
      ) : (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
            <Link to={`/client/summaries/${summary.id}`} className="text-xl font-bold text-ink underline decoration-line-strong decoration-1 underline-offset-4 hover:decoration-ink">
              {summary.title}
            </Link>
            <Badge tone={STATUS_TONE[summary.status]}>{STATUS_LABEL[summary.status]}</Badge>
          </div>
          <p className="num mt-1 text-[0.875rem] text-muted">
            {formatDate(summary.period_start)} – {formatDate(summary.period_end)}
          </p>
          <ul className="mt-4 space-y-3">
            {summary.statements.slice(0, 2).map((s) => {
              const mark = sectionMark(s.section)
              return (
                <li key={s.id} className="flex gap-3">
                  <span className="mt-1.5">{mark ? <Mark kind={mark} size={12} /> : <span className="block h-3 w-3" />}</span>
                  <p className="max-w-[62ch] text-base leading-relaxed text-ink">{s.text}</p>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </section>
  )
}

export function Home() {
  const { state } = useAuth()
  // One "now" per visit keeps the trend window and relative days consistent.
  const now = useMemo(() => new Date(), [])
  const appointments = useLoad(useCallback(() => appointmentsApi.list(), []))
  const summaries = useLoad(useCallback(() => summariesApi.list(), []))
  const name = state.status === 'authed' ? firstName(state.user.display_name) : ''
  const next = appointments.data ? nextAppointment(appointments.data, now) : null

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4 sm:mb-8">
        <div>
          <h1 className="text-[2.25rem] leading-none sm:text-[3rem]">Merhaba {name}.</h1>
          <p className="mt-3 text-base text-ink-2">
            {now.toLocaleDateString('tr-TR', { weekday: 'long', day: 'numeric', month: 'long' })}
            {next && ` · seansın ${relativeDay(next.scheduled_at, now)}`}
          </p>
        </div>
        <LinkButton to="/client/entries?yeni=1">
          <PlusIcon /> Kayıt ekle
        </LinkButton>
      </div>
      <ReminderStrip />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)] lg:gap-5">
        {/* First in reading order on phones: the next session is what the client acts on. */}
        <div className="lg:col-start-2 lg:row-start-1">
          {appointments.error ? (
            <Alert>{appointments.error}</Alert>
          ) : appointments.loading ? (
            <Spinner />
          ) : (
            <NextAppointment appointment={next} summaries={summaries.data ?? []} now={now} />
          )}
        </div>
        <div className="space-y-4 lg:col-start-1 lg:row-start-1 lg:space-y-5">
          <Rhythm now={now} />
          {summaries.error ? <Alert>{summaries.error}</Alert> : summaries.loading ? null : <LastSummary summary={latestSummary(summaries.data ?? [])} />}
        </div>
      </div>
    </div>
  )
}
