import type { TrendDay } from '../lib/trend'
import { Mark } from './Mark'

/** Sleep scale: 10 hours fills the column. */
const SLEEP_MAX = 10
/** Share of the column height a full night may take; attack discs stack above it. */
const SCALE = 74

const DAY = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short' })
const WEEKDAY = new Intl.DateTimeFormat('tr-TR', { weekday: 'long', day: 'numeric', month: 'long' })
const HOURS = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 })

/** The 21-day rhythm: an ochre sleep bar rising from the baseline and, above it, one vermilion
 *  disc per attack whose diameter is that attack's intensity. Decorative for screen readers,
 *  who get the same data as a table. */
export function RhythmStrip({ days }: { days: TrendDay[] }) {
  const last = days.length - 1
  return (
    <figure className="m-0">
      <div aria-hidden>
        <div className="relative grid h-40 items-end gap-[3px] border-b border-ink pr-9 sm:h-52 sm:gap-1.5" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}>
          {/* Hairlines at 4 and 8 hours. */}
          {[4, 8].map((h) => (
            <div key={h} className="pointer-events-none absolute inset-x-0 border-t border-dashed border-line" style={{ bottom: `${(h / SLEEP_MAX) * SCALE}%` }}>
              <span className="num absolute -top-2 right-0 text-[0.6875rem] font-semibold text-muted">{h} sa</span>
            </div>
          ))}
          {days.map((d, i) => (
            <div key={d.key} className="flex h-full min-w-0 flex-col items-center justify-end gap-1">
              <div className="flex w-full flex-col-reverse items-center gap-0.5">
                {d.attacks.map((a, j) => (
                  <span
                    key={j}
                    className="mark-in block aspect-square rounded-full bg-attack"
                    style={{ width: `${35 + a.intensity * 6.5}%`, ['--i' as string]: i }}
                  />
                ))}
              </div>
              <span
                className={`mark-in block w-full rounded-t-[2px] ${d.sleep == null ? 'bg-transparent' : 'bg-sleep'}`}
                style={{ height: d.sleep == null ? 2 : `${(Math.min(d.sleep, SLEEP_MAX) / SLEEP_MAX) * SCALE}%`, ['--i' as string]: i }}
              />
            </div>
          ))}
        </div>
        <div className="mt-2 grid pr-9 text-[0.75rem] font-semibold text-muted" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}>
          {days.map((d, i) => (
            <span key={d.key} className={`num whitespace-nowrap ${i === 0 ? 'justify-self-start' : i === last ? 'justify-self-end text-ink' : 'justify-self-center'}`}>
              {i === 0 ? DAY.format(d.date) : i === last ? 'Bugün' : i % 7 === 0 ? DAY.format(d.date) : ''}
            </span>
          ))}
        </div>
      </div>
      <figcaption className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-[0.875rem] text-ink-2">
        <span className="inline-flex items-center gap-2">
          <Mark kind="sleep" size={14} />
          Uyku (gece başına saat)
        </span>
        <span className="inline-flex items-center gap-2">
          <Mark kind="panic" size={14} />
          Atak, çap = şiddet
        </span>
      </figcaption>
      <table className="sr-only">
        <caption>Son {days.length} gün: uyku ve ataklar</caption>
        <thead>
          <tr>
            <th scope="col">Gün</th>
            <th scope="col">Uyku</th>
            <th scope="col">Ataklar (şiddet)</th>
          </tr>
        </thead>
        <tbody>
          {days.map((d) => (
            <tr key={d.key}>
              <th scope="row">{WEEKDAY.format(d.date)}</th>
              <td>{d.sleep == null ? 'kayıt yok' : `${HOURS.format(d.sleep)} saat`}</td>
              <td>{d.attacks.length ? d.attacks.map((a) => `${a.intensity}/10`).join(', ') : 'yok'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}
