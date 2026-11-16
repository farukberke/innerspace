import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { summariesApi } from '../../api/endpoints'
import type { Summary } from '../../api/types'
import { TopicsSection } from '../../components/TopicsSection'
import { Alert, Badge, Button, Card, formatDate, formatDateTime, PageHeader, Spinner, TextArea, TextField } from '../../components/ui'
import { useLoad } from '../../hooks/useLoad'
import { STATUS_LABEL, STATUS_TONE } from './Summaries'

function Editor({ summary, onSaved }: { summary: Summary; onSaved: (s: Summary) => void }) {
  const [title, setTitle] = useState(summary.title)
  const [texts, setTexts] = useState<Record<string, string>>(() => Object.fromEntries(summary.statements.map((s) => [s.id, s.text])))
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function save() {
    setBusy(true)
    setError(null)
    const statements = summary.statements.filter((s) => texts[s.id] !== s.text).map((s) => ({ id: s.id, text: texts[s.id] }))
    try {
      onSaved(await summariesApi.update(summary.id, { title: title !== summary.title ? title : undefined, statements }))
    } catch (err) {
      // 422 carries the guardrail's reason (e.g. text that reads like a diagnosis or advice).
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      {error && <Alert>{error}</Alert>}
      <TextField label="Başlık" maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
      {summary.statements.map((s, i) => (
        <TextArea
          key={s.id}
          label={`${s.section} — ifade ${i + 1}`}
          hint={`${s.source_entry_ids.length} kayda dayanıyor`}
          maxLength={600}
          rows={3}
          value={texts[s.id] ?? ''}
          onChange={(e) => setTexts((p) => ({ ...p, [s.id]: e.target.value }))}
        />
      ))}
      <Button onClick={save} disabled={busy}>
        {busy ? 'Kaydediliyor…' : 'Değişiklikleri kaydet'}
      </Button>
      <p className="text-xs text-slate-500">Düzenleme özeti taslağa döndürür; yeniden onaylaman gerekir.</p>
    </div>
  )
}

export function SummaryDetail() {
  const { id = '' } = useParams()
  const load = useCallback(() => summariesApi.get(id), [id])
  const { data, error, loading, reload } = useLoad(load)
  const [override, setOverride] = useState<Summary | null>(null)
  const [editing, setEditing] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const summary = override?.id === id ? override : data

  async function act(fn: () => Promise<Summary>) {
    try {
      setOverride(await fn())
      setActionError(null)
    } catch (err) {
      setActionError(errorMessage(err))
      reload()
    }
  }

  if (loading && !summary) return <Spinner />
  if (!summary) return <Alert>{error ?? 'Özet yüklenemedi.'}</Alert>

  return (
    <div>
      <p className="mb-2 text-sm">
        <Link to="/client/summaries" className="text-indigo-700 hover:underline">
          ← Özetlerim
        </Link>
      </p>
      <PageHeader title={summary.title} actions={<Badge tone={STATUS_TONE[summary.status]}>{STATUS_LABEL[summary.status]}</Badge>} />
      <p className="mb-4 text-xs text-slate-500">
        {formatDate(summary.period_start)} – {formatDate(summary.period_end)} · Oluşturuldu: {formatDateTime(summary.created_at)}
      </p>
      {actionError && <Alert>{actionError}</Alert>}
      <Card className="my-4">
        {editing ? (
          <Editor
            summary={summary}
            onSaved={(s) => {
              setOverride(s)
              setEditing(false)
            }}
          />
        ) : (
          <div className="space-y-4">
            {summary.statements.map((s) => (
              <div key={s.id}>
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{s.section}</p>
                <p className="whitespace-pre-wrap break-words text-sm text-slate-800">{s.text}</p>
                <p className="text-xs text-slate-400">{s.source_entry_ids.length} kayda dayanıyor</p>
              </div>
            ))}
          </div>
        )}
      </Card>

      <TopicsSection summary={summary} onSaved={setOverride} />

      {!editing && (
        <div className="flex flex-wrap gap-2">
          {summary.status !== 'shared' && (
            <Button variant="secondary" onClick={() => setEditing(true)}>
              Düzenle
            </Button>
          )}
          {summary.status === 'draft' && <Button onClick={() => act(() => summariesApi.approve(summary.id))}>Onayla</Button>}
          {(summary.status === 'approved' || summary.status === 'revoked') && (
            <Button onClick={() => act(() => summariesApi.share(summary.id))}>Uzmanımla paylaş</Button>
          )}
          {summary.status === 'shared' && (
            <Button variant="danger" onClick={() => act(() => summariesApi.unshare(summary.id))}>
              Paylaşımı geri al
            </Button>
          )}
        </div>
      )}
      <p className="mt-4 text-xs text-slate-500">
        {summary.status === 'draft' && 'Bu taslak yalnızca sana görünür. Onaylamadan paylaşamazsın.'}
        {summary.status === 'approved' && 'Onayladın; henüz kimseyle paylaşılmadı.'}
        {summary.status === 'shared' && `Atanmış uzmanın bu özeti görebilir (paylaşım: ${formatDateTime(summary.shared_at ?? summary.created_at)}).`}
        {summary.status === 'revoked' && 'Paylaşımı geri aldın; uzmanın artık göremez.'}
      </p>
    </div>
  )
}
