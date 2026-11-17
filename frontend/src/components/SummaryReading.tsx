import { Mark, sectionMark } from './Mark'

export interface ReadingSection {
  heading: string | null
  items: { key: string; text: string; sources?: number }[]
}

/** A summary set for reading: one measure-limited column, each section headed by its mark,
 *  each statement with how many of the client's own records it rests on (when known). */
export function SummaryReading({ sections }: { sections: ReadingSection[] }) {
  return (
    <div className="space-y-8">
      {sections.map((sec, i) => {
        const mark = sec.heading ? sectionMark(sec.heading) : null
        return (
          <section key={i} aria-label={sec.heading ?? undefined}>
            {sec.heading && (
              <h2 className="flex items-center gap-2.5 border-b border-ink pb-2 text-[1.0625rem] font-extrabold [font-stretch:110%]">
                {mark && <Mark kind={mark} size={14} />}
                {sec.heading}
              </h2>
            )}
            <ul className="mt-3 space-y-4">
              {sec.items.map((it) => (
                <li key={it.key} className="max-w-[66ch]">
                  <p className="whitespace-pre-wrap break-words text-[1.125rem] leading-[1.6] text-ink">{it.text}</p>
                  {it.sources != null && (
                    <p className="num mt-1 text-[0.875rem] font-semibold text-muted">
                      {it.sources === 0 ? 'Doğrudan bir kayda dayanmıyor' : `${it.sources} kaydına dayanıyor`}
                    </p>
                  )}
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
    const item = { key: s.id, text: s.text, sources: s.source_entry_ids.length }
    if (last && last.heading === s.section) last.items.push(item)
    else out.push({ heading: s.section, items: [item] })
  }
  return out
}
