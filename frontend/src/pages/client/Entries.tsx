import { useCallback, useState } from 'react'
import { errorMessage } from '../../api/client'
import { entriesApi } from '../../api/endpoints'
import type { Entry, EntryKind } from '../../api/types'
import { Alert, Badge, Button, Card, Empty, formatDateTime, PageHeader, SelectField, Spinner } from '../../components/ui'
import { useLoad } from '../../hooks/useLoad'
import { ReminderStrip } from '../../components/ReminderStrip'
import { EntryForm, KIND_LABEL } from './EntryForm'

const PAGE = 10

function detailsLine(e: Entry): string {
  const d = e.details
  switch (e.kind) {
    case 'quick':
      return typeof d.mood === 'number' ? `Ruh hali: ${d.mood}/5` : ''
    case 'panic':
      return `Şiddet: ${String(d.intensity)}/10${d.duration_minutes != null ? ` · ${String(d.duration_minutes)} dk` : ''}`
    case 'medication':
      return `${String(d.medication_name)} · ${d.taken ? 'alındı' : 'alınmadı'}`
    case 'avoidance':
      return `${String(d.situation)} · ${d.avoided ? 'kaçınıldı' : 'kaçınılmadı'}`
  }
}

export function Entries() {
  const [kind, setKind] = useState<EntryKind | ''>('')
  const [offset, setOffset] = useState(0)
  const [editing, setEditing] = useState<Entry | 'new' | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const load = useCallback(() => entriesApi.list({ kind: kind || undefined, limit: PAGE, offset }), [kind, offset])
  const { data, error, loading, reload } = useLoad(load)

  async function remove(e: Entry) {
    if (!window.confirm('Bu kaydı silmek istediğine emin misin? Bu işlem geri alınamaz.')) return
    try {
      await entriesApi.remove(e.id)
      setActionError(null)
      reload()
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }

  const saved = () => {
    setEditing(null)
    reload()
  }

  return (
    <div>
      <PageHeader title="Kayıtlarım" actions={editing ? null : <Button onClick={() => setEditing('new')}>Yeni kayıt</Button>} />
      {!editing && <ReminderStrip />}
      {editing && (
        <Card className="mb-5">
          <EntryForm entry={editing === 'new' ? undefined : editing} onSaved={saved} onCancel={() => setEditing(null)} />
        </Card>
      )}
      <div className="mb-4 max-w-xs">
        <SelectField
          label="Türe göre filtrele"
          value={kind}
          onChange={(e) => {
            setKind(e.target.value as EntryKind | '')
            setOffset(0)
          }}
        >
          <option value="">Tümü</option>
          {(Object.keys(KIND_LABEL) as EntryKind[]).map((k) => (
            <option key={k} value={k}>
              {KIND_LABEL[k]}
            </option>
          ))}
        </SelectField>
      </div>
      {(error || actionError) && <Alert>{error ?? actionError}</Alert>}
      {loading ? (
        <Spinner />
      ) : data && data.items.length === 0 ? (
        <Empty>Henüz kayıt yok. İlk kaydını ekleyerek başlayabilirsin.</Empty>
      ) : (
        <ul className="space-y-3">
          {data?.items.map((e) => (
            <li key={e.id}>
              <Card>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Badge tone="brand">{KIND_LABEL[e.kind]}</Badge>
                    <span className="text-xs text-muted">{formatDateTime(e.occurred_at)}</span>
                  </div>
                  <div className="flex gap-1">
                    <Button variant="ghost" onClick={() => setEditing(e)}>
                      Düzenle
                    </Button>
                    <Button variant="ghost" onClick={() => remove(e)}>
                      Sil
                    </Button>
                  </div>
                </div>
                {detailsLine(e) && <p className="mt-2 text-sm text-ink-2">{detailsLine(e)}</p>}
                {e.note && <p className="mt-1 whitespace-pre-wrap break-words text-sm text-ink-2">{e.note}</p>}
              </Card>
            </li>
          ))}
        </ul>
      )}
      {data && data.total > PAGE && (
        <div className="mt-4 flex items-center justify-between">
          <Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
            Önceki
          </Button>
          <span className="text-xs text-muted">
            {offset + 1}–{Math.min(offset + PAGE, data.total)} / {data.total}
          </span>
          <Button variant="secondary" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>
            Sonraki
          </Button>
        </div>
      )}
    </div>
  )
}
