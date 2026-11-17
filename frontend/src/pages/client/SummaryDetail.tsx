import { useCallback, useState } from 'react'
import { useParams } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { summariesApi } from '../../api/endpoints'
import type { Summary } from '../../api/types'
import { AiDisclaimer } from '../../components/AiDisclaimer'
import { TopicsSection } from '../../components/TopicsSection'
import { groupStatements, SummaryReading } from '../../components/SummaryReading'
import { Alert, BackLink, Badge, Button, formatDate, formatDateTime, Spinner, TextArea, TextField } from '../../components/ui'
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
      <p className="text-xs text-muted">Düzenleme özeti taslağa döndürür; yeniden onaylaman gerekir.</p>
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

  const explanation = {
    draft: 'Bu taslak yalnızca sana görünür. Okuyup gerekirse düzenle, sonra onayla.',
    approved: 'Onayladın; henüz kimseyle paylaşılmadı. Paylaştığında atanmış uzmanın görebilir.',
    shared: `Atanmış uzmanın bu özeti görebilir (paylaşım: ${formatDateTime(summary.shared_at ?? summary.created_at)}). İstediğin an geri alabilirsin.`,
    revoked: 'Paylaşımı geri aldın; uzmanın artık göremez. İstersen yeniden paylaşabilirsin.',
  }[summary.status]

  return (
    <div>
      <BackLink to="/client/summaries">Özetlerim</BackLink>
      <header className="mb-8 border-b border-line pb-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-[2rem] leading-[1.05] sm:text-[2.75rem]">{summary.title}</h1>
          <Badge tone={STATUS_TONE[summary.status]}>{STATUS_LABEL[summary.status]}</Badge>
        </div>
        <p className="num mt-3 text-base text-ink-2">
          {formatDate(summary.period_start)} – {formatDate(summary.period_end)}
          <span className="text-muted"> · oluşturuldu {formatDateTime(summary.created_at)}</span>
        </p>
      </header>
      {actionError && (
        <div className="mb-4">
          <Alert>{actionError}</Alert>
        </div>
      )}
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-12">
        <div className="min-w-0">
          {editing ? (
            <div className="rounded-soft-lg border border-line bg-surface p-5">
              <Editor
                summary={summary}
                onSaved={(s) => {
                  setOverride(s)
                  setEditing(false)
                }}
              />
            </div>
          ) : (
            <SummaryReading sections={groupStatements(summary.statements)} />
          )}
          <div className="mt-8">
            <TopicsSection summary={summary} onSaved={setOverride} />
          </div>
        </div>
        <aside className="lg:sticky lg:top-8 lg:self-start">
          <div className="rounded-soft-lg border border-line bg-surface p-5">
            <h2 className="text-lg font-extrabold">Paylaşım</h2>
            <p className="mt-2 text-[0.9375rem] leading-relaxed text-ink-2">{explanation}</p>
            {!editing && (
              <div className="mt-4 flex flex-col gap-2">
                {summary.status === 'draft' && <Button onClick={() => act(() => summariesApi.approve(summary.id))}>Onayla</Button>}
                {(summary.status === 'approved' || summary.status === 'revoked') && (
                  <Button onClick={() => act(() => summariesApi.share(summary.id))}>Uzmanımla paylaş</Button>
                )}
                {summary.status === 'shared' && (
                  <Button variant="secondary" onClick={() => act(() => summariesApi.unshare(summary.id))}>
                    Paylaşımı geri al
                  </Button>
                )}
                {summary.status !== 'shared' && (
                  <Button variant="secondary" onClick={() => setEditing(true)}>
                    Düzenle
                  </Button>
                )}
              </div>
            )}
            <AiDisclaimer audience="client" />
          </div>
        </aside>
      </div>
    </div>
  )
}
