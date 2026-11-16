import { Link } from 'react-router-dom'
import type { CrisisInfo } from '../api/types'
import { telHref } from '../pages/client/Moment'
import { Button } from './ui'

/** Fixed, calm screen shown when the backend reports crisis language. Text comes from the backend. */
export function CrisisScreen({ crisis, onClose }: { crisis: CrisisInfo; onClose?: () => void }) {
  return (
    <section
      role="alert"
      aria-labelledby="crisis-title"
      className="rounded-soft-lg border-2 border-warn-300 bg-warn-50 p-6 text-ink sm:p-10"
    >
      <h2 id="crisis-title" className="text-3xl font-semibold sm:text-4xl">
        Senin için buradayız
      </h2>
      {crisis.resources.length > 0 && (
        <ul className="mt-4 space-y-2">
          {crisis.resources.map((r) => (
            <li key={`${r.name}-${r.contact}`} className="flex flex-wrap items-baseline justify-between gap-2 min-h-14 rounded-soft bg-surface px-4 py-3">
              <span className="text-lg">{r.name}</span>
              <span className="text-2xl font-semibold">{r.contact}</span>
            </li>
          ))}
        </ul>
      )}
      {crisis.contacts && crisis.contacts.length > 0 && (
        <div className="mt-5">
          <h3 className="text-xl font-semibold">Planındaki kişiler</h3>
          <ul className="mt-2 space-y-2">
            {crisis.contacts.map((c, i) => (
              <li key={i}>
                <a href={telHref(c.phone)} className="flex flex-wrap items-baseline justify-between gap-2 min-h-14 rounded-soft bg-surface px-4 py-3 hover:bg-warn-100">
                  <span className="text-lg">{c.name}</span>
                  <span className="text-2xl font-semibold">{c.phone}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-6 text-xl leading-relaxed">{crisis.message}</p>
      <p className="mt-4 text-base">
        <Link to="/client/moment" className="link inline-flex min-h-11 items-center">
          “O an” kartını aç
        </Link>
      </p>
      {onClose && (
        <Button variant="secondary" onClick={onClose} className="mt-5">
          Anladım, geri dön
        </Button>
      )}
    </section>
  )
}
