import { useCallback, useEffect, useState } from 'react'
import { errorMessage } from '../api/client'

interface Result<T> {
  source: unknown
  tick: number
  data: T | null
  error: string | null
}

/** Loads data when `load` (a stable, memoised function) or `reload()` changes. */
export function useLoad<T>(load: () => Promise<T>) {
  const [tick, setTick] = useState(0)
  const [result, setResult] = useState<Result<T> | null>(null)

  useEffect(() => {
    let cancelled = false
    load().then(
      (data) => !cancelled && setResult({ source: load, tick, data, error: null }),
      (err) => !cancelled && setResult({ source: load, tick, data: null, error: errorMessage(err) }),
    )
    return () => {
      cancelled = true
    }
  }, [load, tick])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  const fresh = result !== null && result.source === load && result.tick === tick
  return {
    data: result?.data ?? null,
    error: fresh ? result.error : null,
    loading: !fresh && result?.data == null,
    reload,
  }
}
