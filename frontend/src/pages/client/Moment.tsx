import { useCallback } from 'react'
import { Link } from 'react-router-dom'
import { planApi } from '../../api/endpoints'
import type { PlanContent } from '../../api/types'
import { Alert, Spinner } from '../../components/ui'
import { useLoad } from '../../hooks/useLoad'

/** `tel:` href from a phone the backend already restricted to digits and phone punctuation. */
export const telHref = (phone: string) => `tel:${phone.replace(/[^0-9+]/g, '')}`

/** Large-type "O an" card: the client's own steps, note and contacts. Always offers 112. */
export function MomentCard({ plan }: { plan: PlanContent | null }) {
  const empty = !plan || (plan.moment_steps.length === 0 && !plan.self_note && plan.contacts.length === 0)
  return (
    <div className="space-y-6 text-ink">
      {empty && (
        <p className="text-xl">
          Henüz bir planın yok. Sakin olduğunda <Link to="/client/plan" className="link">Planım</Link> sayfasından hazırlayabilirsin.
        </p>
      )}
      {plan && plan.moment_steps.length > 0 && (
        <section aria-labelledby="moment-steps">
          <h2 id="moment-steps" className="text-2xl font-semibold">
            Şimdi yapacaklarım
          </h2>
          <ol className="mt-3 list-decimal space-y-3 pl-7 text-3xl leading-snug sm:text-4xl">
            {plan.moment_steps.map((s, i) => (
              <li key={i} className="break-words">
                {s}
              </li>
            ))}
          </ol>
        </section>
      )}
      {plan?.self_note && (
        <section aria-labelledby="moment-note" className="rounded-soft-lg bg-brand-50 p-6">
          <h2 id="moment-note" className="text-base font-semibold text-brand-800">
            Kendime not
          </h2>
          <p className="mt-2 whitespace-pre-wrap break-words text-3xl leading-snug sm:text-4xl">{plan.self_note}</p>
        </section>
      )}
      <section aria-labelledby="moment-contacts">
        <h2 id="moment-contacts" className="text-2xl font-semibold">
          Arayabileceklerim
        </h2>
        <ul className="mt-3 space-y-3">
          {plan?.contacts.map((c, i) => (
            <li key={i}>
              <a href={telHref(c.phone)} className="flex items-center justify-between gap-3 lift min-h-16 rounded-soft-lg bg-surface px-5 py-4 text-2xl font-semibold ring-2 ring-line-strong hover:bg-sunk">
                <span className="break-words">{c.name}</span>
                <span className="whitespace-nowrap text-brand-700">{c.phone}</span>
              </a>
            </li>
          ))}
          <li>
            <a href="tel:112" className="flex items-center justify-between gap-3 min-h-16 rounded-soft-lg bg-danger-700 px-5 py-4 text-2xl font-semibold text-white hover:bg-danger-800">
              <span>Acil durum</span>
              <span>112</span>
            </a>
          </li>
        </ul>
      </section>
    </div>
  )
}

export function Moment() {
  const load = useCallback(() => planApi.get(), [])
  const { data, error, loading } = useLoad(load)
  return (
    <div>
      <h1 className="mb-6 text-4xl font-semibold text-ink sm:text-5xl">O an</h1>
      {loading ? <Spinner /> : <MomentCard plan={data} />}
      {error && (
        <div className="mt-4">
          <Alert>Planın yüklenemedi; yine de 112’yi arayabilirsin.</Alert>
        </div>
      )}
    </div>
  )
}
