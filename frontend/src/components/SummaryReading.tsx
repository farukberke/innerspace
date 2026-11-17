import { useCallback, useId, useState } from 'react'
import { entriesApi } from '../api/endpoints'
import type { Entry } from '../api/types'
import { useLoad } from '../hooks/useLoad'
import { Mark, sectionMark } from './Mark'
import { formatDateTime } from './ui'

export interface ReadingSection {
  heading: string | null
  items: { key: string; text: string; sourceIds?: string[] }[]
}

const KIND: Record<Entry['kind'], string> = { quick: 'Günlük', panic: 'Atak', medication: 'İlaç', avoidance: 'Kaçınma' }

/** The client's own records a statement rests on, loaded only when asked for. A record deleted
 *  since the summary was made simply no longer appears. */
function SourceEntries({ ids }: { ids: string[] }) {
  const load = useCallback(
    () => Promise.all(ids.map((id) => entriesApi.get(id).catch(() => null))).then((xs) => xs.filter((x): x is Entry => x !== null)),
    [ids],
  )
  const { data, loading } = useLoad(load)
  if (loading) return <p className="mt-2 text-[0.875rem] text-muted">Kayıtlar yükleniyor…</p>
  if (!data || data.length === 0) return <p className="mt-2 text-[0.875rem] text-muted">Bu kayıtlar artık yok.</p>
  return (
    <ul className="mt-2 space-y-2 border-l border-line pl-4">
      {[...data]
        .sort((a, b) => a.occurred_at.localeCompare(b.occurred_at))
        .map((e) => (
          <li key={e.id} className="flex gap-3 text-[0.9375rem]">
            <span className="mt-1">
              <Mark kind={e.kind} size={12} />
            </span>
            <span className="min-w-0">
              <span className="num font-semibold text-ink">
                {KIND[e.kind]} · {formatDateTime(e.occurred_at)}
              </span>
              {e.note && <span className="block break-words text-ink-2">{e.note}</span>}
            </span>
          </li>
        ))}
    </ul>
  )
}

function Sources({ ids }: { ids: string[] }) {
  const [open, setOpen] = useState(false)
  const panel = useId()
  if (ids.length === 0) return <p className="mt-1 text-[0.875rem] font-semibold text-muted">Doğrudan bir kayda dayanmıyor</p>
  return (
    <div className="mt-1">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panel}
        onClick={() => setOpen((o) => !o)}
        className="num inline-flex min-h-9 items-center gap-1.5 rounded-soft text-[0.875rem] font-bold text-brand-700 hover:text-brand-900"
      >
        {ids.length} kaydına dayanıyor
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden className={`transition-transform ${open ? 'rotate-180' : ''}`}>
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      <div id={panel}>{open && <SourceEntries ids={ids} />}</div>
    </div>
  )
}

/** A summary set for reading: one measure-limited column, each section headed by its mark.
 *  On the client's own view each statement can open the records it rests on. */
export function SummaryReading({ sections }: { sections: ReadingSection[] }) {
  return (
    <div className="space-y-8">
      {sections.map((sec, i) => {
        const mark = sec.heading ? sectionMark(sec.heading) : null
        return (
          <section key={i} aria-label={sec.heading ?? undefined}>
            {sec.heading && (
              <h2 className="flex items-center gap-2.5 border-b border-ink pb-2 text-[1.0625rem] font-extrabold">
                {mark && <Mark kind={mark} size={14} />}
                {sec.heading}
              </h2>
            )}
            <ul className="mt-3 space-y-4">
              {sec.items.map((it) => (
                <li key={it.key} className="max-w-[66ch]">
                  <p className="whitespace-pre-wrap break-words text-[1.125rem] leading-[1.6] text-ink">{it.text}</p>
                  {it.sourceIds && <Sources ids={it.sourceIds} />}
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}

/** Groups consecutive statements by section, keeping the backend's order. */
export function groupStatements(statements: { id: string; section: string; text: string; source_entry_ids: string[] }[]): ReadingSection[] {
  const out: ReadingSection[] = []
  for (const s of statements) {
    const last = out[out.length - 1]
    const item = { key: s.id, text: s.text, sourceIds: s.source_entry_ids }
    if (last && last.heading === s.section) last.items.push(item)
    else out.push({ heading: s.section, items: [item] })
  }
  return out
}
