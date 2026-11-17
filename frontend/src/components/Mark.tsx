import type { EntryKind } from '../api/types'

/** The product's mark language: every record kind owns one shape and colour, used wherever
 *  records are referenced (rhythm strip, entry list, summary sources, legends). */
export type MarkKind = EntryKind | 'sleep'

export const MARK_LABEL: Record<MarkKind, string> = {
  quick: 'Günlük not',
  panic: 'Atak',
  medication: 'İlaç',
  avoidance: 'Kaçınma',
  sleep: 'Uyku',
}

export function Mark({ kind, size = 14, className = '' }: { kind: MarkKind; size?: number; className?: string }) {
  const common = { width: size, height: size, viewBox: '0 0 16 16', 'aria-hidden': true, className: `shrink-0 ${className}` }
  switch (kind) {
    case 'panic':
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="8" fill="var(--color-attack)" />
        </svg>
      )
    case 'quick':
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="6" fill="var(--color-brand-600)" />
        </svg>
      )
    case 'medication':
      return (
        <svg {...common}>
          <rect x="2" y="2" width="12" height="12" rx="1" fill="var(--color-med)" />
        </svg>
      )
    case 'avoidance':
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="6" fill="none" stroke="var(--color-ink)" strokeWidth="2.5" />
        </svg>
      )
    case 'sleep':
      return (
        <svg {...common}>
          <rect x="4" y="1" width="8" height="15" rx="1" fill="var(--color-sleep)" />
        </svg>
      )
  }
}

/** Summary sections come back as free-text headings; map the known ones to their mark. */
export function sectionMark(section: string): MarkKind | null {
  const s = section.toLocaleLowerCase('tr-TR')
  if (s.includes('atak') || s.includes('panik')) return 'panic'
  if (s.includes('ilaç') || s.includes('yan etki')) return 'medication'
  if (s.includes('kaçın')) return 'avoidance'
  if (s.includes('uyku')) return 'sleep'
  if (s.includes('günlük') || s.includes('not')) return 'quick'
  return null
}
