import { Link } from 'react-router-dom'
import type { CrisisInfo } from '../api/types'
import { telHref } from '../pages/client/Moment'

/** Fixed, calm screen shown when the backend reports crisis language. Text comes from the backend. */
export function CrisisScreen({ crisis, onClose }: { crisis: CrisisInfo; onClose?: () => void }) {
  return (
    <section
      role="alert"
      aria-labelledby="crisis-title"
      className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-slate-800 sm:p-8"
    >
      <h2 id="crisis-title" className="text-lg font-semibold">
        Senin için buradayız
      </h2>
      <p className="mt-3 leading-relaxed">{crisis.message}</p>
      {crisis.resources.length > 0 && (
        <ul className="mt-4 space-y-2">
          {crisis.resources.map((r) => (
            <li key={`${r.name}-${r.contact}`} className="flex flex-wrap items-baseline justify-between gap-2 rounded-lg bg-white px-4 py-3">
              <span className="text-sm">{r.name}</span>
              <span className="text-lg font-semibold">{r.contact}</span>
            </li>
          ))}
        </ul>
      )}
      {crisis.contacts && crisis.contacts.length > 0 && (
        <div className="mt-5">
          <h3 className="text-sm font-semibold">Planındaki kişiler</h3>
          <ul className="mt-2 space-y-2">
            {crisis.contacts.map((c, i) => (
              <li key={i}>
                <a href={telHref(c.phone)} className="flex flex-wrap items-baseline justify-between gap-2 rounded-lg bg-white px-4 py-3 hover:bg-amber-100">
                  <span className="text-sm">{c.name}</span>
                  <span className="text-lg font-semibold">{c.phone}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-4 text-sm">
        <Link to="/client/moment" className="font-medium underline">
          “O an” kartını aç
        </Link>
      </p>
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          className="mt-5 rounded-lg border border-amber-300 bg-white px-4 py-2 text-sm font-medium hover:bg-amber-100"
        >
          Anladım, geri dön
        </button>
      )}
    </section>
  )
}
