import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { clinicianApi } from '../../api/endpoints'
import { Alert, Button, Card, Empty, formatDate, formatDateTime, PageHeader, Spinner } from '../../components/ui'
import { useLoad } from '../../hooks/useLoad'
import { InviteForm } from '../InviteForm'

export function ClinicianClients() {
  const [inviting, setInviting] = useState(false)
  const load = useCallback(() => clinicianApi.clients(), [])
  const { data, error, loading } = useLoad(load)
  return (
    <div>
      <PageHeader title="Danışanlarım" actions={<Button onClick={() => setInviting((i) => !i)}>{inviting ? 'Kapat' : 'Danışan davet et'}</Button>} />
      {inviting && (
        <div className="mb-5">
          <InviteForm roles={['client']} />
        </div>
      )}
      {error && <Alert>{error}</Alert>}
      {loading ? (
        <Spinner />
      ) : data && data.length === 0 ? (
        <Empty>Sana atanmış danışan yok.</Empty>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {data?.map((c) => (
            <li key={c.id}>
              <Card>{c.display_name}</Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function ClinicianSummaries() {
  const summaries = useLoad(useCallback(() => clinicianApi.summaries(), []))
  const clients = useLoad(useCallback(() => clinicianApi.clients(), []))
  const names = new Map(clients.data?.map((c) => [c.id, c.display_name]))
  return (
    <div>
      <PageHeader title="Paylaşılan özetler" />
      {summaries.error && <Alert>{summaries.error}</Alert>}
      {summaries.loading ? (
        <Spinner />
      ) : summaries.data && summaries.data.length === 0 ? (
        <Empty>Danışanların henüz seninle özet paylaşmadı.</Empty>
      ) : (
        <ul className="space-y-3">
          {summaries.data?.map((s) => (
            <li key={s.id}>
              <Card>
                <Link to={`/clinician/summaries/${s.id}`} className="font-medium text-indigo-700 hover:underline">
                  {s.title}
                </Link>
                <p className="mt-1 text-xs text-slate-500">
                  {names.get(s.client_id) ?? 'Danışan'} · {formatDate(s.period_start)} – {formatDate(s.period_end)} · Paylaşım:{' '}
                  {s.shared_at ? formatDateTime(s.shared_at) : '—'}
                </p>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function ClinicianSummaryDetail() {
  const { id = '' } = useParams()
  const { data, error, loading } = useLoad(useCallback(() => clinicianApi.summary(id), [id]))
  if (loading) return <Spinner />
  if (!data) return <Alert>{error ?? 'Özet yüklenemedi.'}</Alert>
  return (
    <div>
      <p className="mb-2 text-sm">
        <Link to="/clinician/summaries" className="text-indigo-700 hover:underline">
          ← Paylaşılan özetler
        </Link>
      </p>
      <PageHeader title={data.title} />
      <p className="mb-4 text-xs text-slate-500">
        {formatDate(data.period_start)} – {formatDate(data.period_end)}
      </p>
      <Card>
        <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-800">{data.body}</p>
      </Card>
      <p className="mt-3 text-xs text-slate-500">Bu özet danışan tarafından onaylanıp seninle paylaşıldı; danışan paylaşımı geri alabilir.</p>
    </div>
  )
}
