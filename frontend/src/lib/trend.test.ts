import { describe, expect, it } from 'vitest'
import type { Entry } from '../api/types'
import { buildTrend, formatDelta, trendStats, windowStart } from './trend'

const NOW = new Date(2026, 10, 17, 15, 0) // 17 Nov 2026, local time

function entry(kind: Entry['kind'], daysAgo: number, details: Record<string, unknown>): Entry {
  const at = new Date(2026, 10, 17 - daysAgo, 9, 30)
  return {
    id: `${kind}-${daysAgo}-${JSON.stringify(details)}`,
    kind,
    occurred_at: at.toISOString(),
    note: null,
    details,
    created_at: at.toISOString(),
    updated_at: at.toISOString(),
  }
}

describe('trend', () => {
  it('builds 21 local days ending today, oldest first', () => {
    const days = buildTrend([], NOW)
    expect(days).toHaveLength(21)
    expect(days[0].key).toBe('2026-10-28')
    expect(days[20].key).toBe('2026-11-17')
    expect(windowStart(NOW).getDate()).toBe(28)
  })

  it('averages sleep per day, collects attacks and ignores entries outside the window', () => {
    const days = buildTrend(
      [
        entry('quick', 0, { mood: 3, sleep_hours: 6 }),
        entry('quick', 0, { sleep_hours: 7 }),
        entry('quick', 1, { mood: 2 }), // no sleep recorded
        entry('panic', 1, { intensity: 7, duration_minutes: 10 }),
        entry('panic', 1, { intensity: 4 }),
        entry('medication', 2, { medication_name: 'A', taken: true }),
        entry('quick', 30, { sleep_hours: 2 }), // before the window
      ],
      NOW,
    )
    expect(days[20].sleep).toBe(6.5)
    expect(days[19].sleep).toBeNull()
    expect(days[19].attacks).toEqual([
      { intensity: 7, minutes: 10 },
      { intensity: 4, minutes: null },
    ])
    expect(days.flatMap((d) => d.attacks)).toHaveLength(2)
  })

  it('summarises the window and compares the last week with the two before', () => {
    const entries = [
      ...[0, 1, 2].map((d) => entry('quick', d, { sleep_hours: 7 })),
      ...[10, 12].map((d) => entry('quick', d, { sleep_hours: 6 })),
      entry('panic', 4, { intensity: 8 }),
      entry('panic', 12, { intensity: 6 }),
    ]
    const stats = trendStats(buildTrend(entries, NOW))
    expect(stats.attackCount).toBe(2)
    expect(stats.meanIntensity).toBe(7)
    expect(stats.meanSleep).toBeCloseTo(6.6)
    expect(stats.sleepDelta).toBeCloseTo(1)
    expect(stats.daysWithRecords).toBe(6)
  })

  it('has no comparison when one side of it is empty', () => {
    const stats = trendStats(buildTrend([entry('quick', 0, { sleep_hours: 7 })], NOW))
    expect(stats.sleepDelta).toBeNull()
    expect(stats.meanIntensity).toBeNull()
  })

  it('formats deltas with a real minus sign', () => {
    expect(formatDelta(0.5)).toBe('+0,5 sa')
    expect(formatDelta(-1.25)).toBe('−1,3 sa')
    expect(formatDelta(0.01)).toBe('değişmedi')
  })
})
