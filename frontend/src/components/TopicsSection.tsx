import { useState } from 'react'
import { errorMessage } from '../api/client'
import { summariesApi } from '../api/endpoints'
import type { CrisisInfo, Summary } from '../api/types'
import { CrisisScreen } from './CrisisScreen'
import { Alert, Button, Card, TextField } from './ui'

const MAX_TOPICS = 10
const MAX_LEN = 200

function isCrisis(r: Summary | CrisisInfo): r is CrisisInfo {
  return 'crisis' in r && r.crisis === true
}

/** "Konuşmak istediğim konular": the client's own items, written by hand (never AI). The
 *  backend applies the same guardrails as for AI text; shared summaries cannot be edited. */
export function TopicsSection({ summary, onSaved }: { summary: Summary; onSaved: (s: Summary) => void }) {
  const [editing, setEditing] = useState(false)
  const [items, setItems] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [crisis, setCrisis] = useState<CrisisInfo | null>(null)
  const [busy, setBusy] = useState(false)
  const shared = summary.status === 'shared'

  function start() {
    setItems(summary.topics.length > 0 ? summary.topics : [''])
    setError(null)
    setEditing(true)
  }

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const result = await summariesApi.setTopics(
        summary.id,
        items.map((t) => t.trim()).filter((t) => t !== ''),
      )
      if (isCrisis(result)) {
        setCrisis(result)
        setEditing(false)
      } else {
        onSaved(result)
        setEditing(false)
      }
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (crisis) return <CrisisScreen crisis={crisis} onClose={() => setCrisis(null)} />

  return (
    <section aria-labelledby="topics-title">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="topics-title" className="text-[1.0625rem] font-extrabold text-ink">
            Konuşmak istediğim konular
          </h2>
          {!editing && !shared && (
            <Button variant="secondary" onClick={start}>
              {summary.topics.length > 0 ? 'Konuları düzenle' : 'Konu ekle'}
            </Button>
          )}
        </div>
        {editing ? (
          <div className="mt-3 space-y-3">
            {error && <Alert>{error}</Alert>}
            {items.map((t, i) => (
              <div key={i} className="flex items-end gap-2">
                <div className="flex-1">
                  <TextField
                    label={`Konu ${i + 1}`}
                    maxLength={MAX_LEN}
                    value={t}
                    onChange={(e) => setItems((p) => p.map((x, j) => (j === i ? e.target.value : x)))}
                  />
                </div>
                <Button variant="ghost" aria-label={`Konu ${i + 1} sil`} onClick={() => setItems((p) => p.filter((_, j) => j !== i))}>
                  Sil
                </Button>
              </div>
            ))}
            <div className="flex flex-wrap gap-2">
              {items.length < MAX_TOPICS && (
                <Button variant="secondary" onClick={() => setItems((p) => [...p, ''])}>
                  Başka konu ekle
                </Button>
              )}
              <Button onClick={save} disabled={busy}>
                {busy ? 'Kaydediliyor…' : 'Konuları kaydet'}
              </Button>
              <Button variant="ghost" onClick={() => setEditing(false)} disabled={busy}>
                Vazgeç
              </Button>
            </div>
            <p className="text-xs text-muted">En fazla {MAX_TOPICS} konu, her biri {MAX_LEN} karakter. Kaydetmek özeti taslağa döndürür; yeniden onaylaman gerekir.</p>
          </div>
        ) : summary.topics.length > 0 ? (
          <ul className="mt-3 list-disc space-y-1.5 pl-5 text-base text-ink marker:text-brand-600">
            {summary.topics.map((t, i) => (
              <li key={i} className="break-words">
                {t}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-muted">Seansta konuşmak istediğin konuları kendi cümlelerinle ekleyebilirsin.</p>
        )}
        {shared && <p className="mt-2 text-xs text-muted">Konuları değiştirmek için önce paylaşımı geri al.</p>}
      </Card>
    </section>
  )
}
