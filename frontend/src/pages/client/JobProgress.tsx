import { Link } from 'react-router-dom'
import type { SummaryJob } from '../../api/types'
import { CrisisScreen } from '../../components/CrisisScreen'
import { Alert, Button } from '../../components/ui'
import { useJobPolling } from '../../hooks/useJobPolling'

const FAILURE_TEXT: Record<string, string> = {
  no_entries: 'Seçtiğin tarih aralığında kayıt bulunamadı.',
  enqueue_failed: 'Özet işlemi başlatılamadı. Lütfen daha sonra tekrar dene.',
}

/** Follows a summary job to its end: succeeded, crisis (fixed screen) or failed. */
export function JobProgress({
  initial,
  intervalMs,
  onReset,
}: {
  initial: SummaryJob
  intervalMs?: number
  onReset: () => void
}) {
  const { job, error } = useJobPolling(initial, intervalMs)
  if (!job) return null

  if (job.status === 'crisis') {
    return job.crisis ? <CrisisScreen crisis={job.crisis} onClose={onReset} /> : null
  }
  if (job.status === 'succeeded') {
    return (
      <Alert kind="success">
        <p>Özet taslağın hazır. Paylaşmadan önce gözden geçirip onaylaman gerekiyor.</p>
        {job.summary_id && (
          <Link to={`/client/summaries/${job.summary_id}`} className="link mt-2 inline-flex min-h-11 items-center">
            Taslağı aç
          </Link>
        )}
      </Alert>
    )
  }
  if (job.status === 'failed') {
    return (
      <div className="space-y-3">
        <Alert>
          {(job.error_code && FAILURE_TEXT[job.error_code]) ??
            'Özet şu anda oluşturulamadı. Lütfen daha sonra tekrar dene.'}
        </Alert>
        <Button variant="secondary" onClick={onReset}>
          Tekrar dene
        </Button>
      </div>
    )
  }
  return (
    <div className="space-y-2">
      <Alert kind="info">Özetin hazırlanıyor. Bu birkaç saniye sürebilir…</Alert>
      {error && <Alert>{error}</Alert>}
    </div>
  )
}
