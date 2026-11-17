import { entriesApi } from '../api/endpoints'
import type { Entry } from '../api/types'

export const TREND_DAYS = 21

export interface Attack {
  intensity: number
  minutes: number | null
}

export interface TrendDay {
  /** Local calendar day, YYYY-MM-DD. */
  key: string
  date: Date
  /** Average of the day's recorded nights (quick entries with sleep_hours), or null. */
  sleep: number | null
  attacks: Attack[]
}

export interface TrendStats {
  attackCount: number
  /** Mean attack intensity (0-10), null without attacks. */
  meanIntensity: number | null
  /** Mean recorded sleep across the whole window, null when nothing was recorded. */
  meanSleep: number | null
  /** Mean sleep of the last 7 days minus the 14 days before; null if either side is empty. */
  sleepDelta: number | null
  daysWithRecords: number
}

function dayKey(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

/** First instant of the window: local midnight `days - 1` days before `now`. */
export function windowStart(now: Date, days = TREND_DAYS): Date {
  const start = startOfDay(now)
  start.setDate(start.getDate() - (days - 1))
  return start
}

function mean(values: number[]): number | null {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null
}

/** Buckets entries into `days` local calendar days ending today (oldest first). */
export function buildTrend(entries: Entry[], now: Date, days = TREND_DAYS): TrendDay[] {
  const start = windowStart(now, days)
  const out: TrendDay[] = []
  const byKey = new Map<string, { sleeps: number[]; attacks: Attack[] }>()
  for (let i = 0; i < days; i++) {
    const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i)
    const key = dayKey(date)
    byKey.set(key, { sleeps: [], attacks: [] })
    out.push({ key, date, sleep: null, attacks: [] })
  }
  for (const e of entries) {
    const bucket = byKey.get(dayKey(new Date(e.occurred_at)))
    if (!bucket) continue
    if (e.kind === 'quick' && typeof e.details.sleep_hours === 'number') bucket.sleeps.push(e.details.sleep_hours)
    if (e.kind === 'panic' && typeof e.details.intensity === 'number') {
      const minutes = e.details.duration_minutes
      bucket.attacks.push({ intensity: e.details.intensity, minutes: typeof minutes === 'number' ? minutes : null })
    }
  }
  return out.map((d) => {
    const bucket = byKey.get(d.key)!
    return { ...d, sleep: mean(bucket.sleeps), attacks: bucket.attacks }
  })
}

export function trendStats(days: TrendDay[]): TrendStats {
  const attacks = days.flatMap((d) => d.attacks)
  const sleeps = (part: TrendDay[]) => part.flatMap((d) => (d.sleep == null ? [] : [d.sleep]))
  const recent = mean(sleeps(days.slice(-7)))
  const before = mean(sleeps(days.slice(0, -7)))
  return {
    attackCount: attacks.length,
    meanIntensity: mean(attacks.map((a) => a.intensity)),
    meanSleep: mean(sleeps(days)),
    sleepDelta: recent != null && before != null ? recent - before : null,
    daysWithRecords: days.filter((d) => d.sleep != null || d.attacks.length > 0).length,
  }
}

/** All entries of the window (pages of 100; the backend caps a page there). */
export async function loadTrendEntries(now: Date, days = TREND_DAYS): Promise<Entry[]> {
  const from = windowStart(now, days).toISOString()
  const items: Entry[] = []
  for (let offset = 0; offset < 1000; offset += 100) {
    const page = await entriesApi.list({ from, limit: 100, offset })
    items.push(...page.items)
    if (items.length >= page.total || page.items.length === 0) break
  }
  return items
}

const ONE_DECIMAL = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })

export function formatHours(value: number): string {
  return `${ONE_DECIMAL.format(value)} sa`
}

export function formatDelta(value: number): string {
  if (Math.abs(value) < 0.05) return 'değişmedi'
  return `${value > 0 ? '+' : '−'}${ONE_DECIMAL.format(Math.abs(value))} sa`
}
