import { useCallback, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { entriesApi } from '../../api/endpoints'
import type { Entry, EntryKind } from '../../api/types'
import { PlusIcon } from '../../components/icons'
import { Mark } from '../../components/Mark'
import { Alert, Button, Card, Empty, formatDateTime, PageHeader, SelectField, Spinner } from '../../components/ui'
import { useLoad } from '../../hooks/useLoad'
import { ReminderStrip } from '../../components/ReminderStrip'
import { EntryForm, KIND_LABEL } from './EntryForm'

const PAGE = 10

function detailsLine(e: Entry): string {
  const d = e.details
  switch (e.kind) {
    case 'quick':
      return [
        typeof d.mood === 'number' ? `Ruh hali ${d.mood}/5` : '',
        typeof d.sleep_hours === 'number' ? `Uyku ${String(d.sleep_hours).replace('.', ',')} sa` : '',
      ]
        .filter(Boolean)
        .join(' · ')
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
  // The home page's "Kayıt ekle" links here with ?yeni=1.
  const [params] = useSearchParams()
  const [editing, setEditing] = useState<Entry | 'new' | null>(params.get('yeni') ? 'new' : null)
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
      <PageHeader
        title="Kayıtlarım"
        lede="Yalnızca sen görürsün. Özet hazırladığında bu kayıtlardan alıntı yapılır."
        actions={
          editing ? null : (
            <Button onClick={() => setEditing('new')}>
              <PlusIcon /> Yeni kayıt
            </Button>
          )
        }
      />
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
        kind ? (
          <Empty title="Bu türde kayıt yok">Filtreyi “Tümü” yaparak diğer kayıtlarını görebilirsin.</Empty>
        ) : (
          <Empty
            title="Defterin boş"
            action={
              editing ? null : (
                <Button onClick={() => setEditing('new')}>
                  <PlusIcon /> İlk kaydı ekle
                </Button>
              )
            }
          >
            Bir gün nasıl geçti, bir atak, ilacın ya da kaçındığın bir durum: 30 saniyelik bir kayıt yeter. Seansa hazırlanırken buradan derlenir.
          </Empty>
        )
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-soft-lg border border-line bg-surface">
          {data?.items.map((e) => (
            <li key={e.id} className="flex gap-4 px-4 py-3 sm:px-5">
              <span className="mt-2.5">
                <Mark kind={e.kind} size={16} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                  <p className="font-bold text-ink">
                    {KIND_LABEL[e.kind]}
                    {detailsLine(e) && <span className="font-normal text-ink-2"> · {detailsLine(e)}</span>}
                  </p>
                  <div className="flex w-full items-center justify-between gap-1 sm:w-auto sm:justify-end">
                    <span className="num mr-2 whitespace-nowrap text-[0.875rem] text-muted">{formatDateTime(e.occurred_at)}</span>
                    <Button variant="ghost" className="min-h-10 px-2.5" onClick={() => setEditing(e)} aria-label={`${KIND_LABEL[e.kind]} kaydını düzenle`}>
                      Düzenle
                    </Button>
                    <Button variant="ghost" className="min-h-10 px-2.5" onClick={() => remove(e)} aria-label={`${KIND_LABEL[e.kind]} kaydını sil`}>
                      Sil
                    </Button>
                  </div>
                </div>
                {e.note && <p className="mt-1 max-w-[70ch] whitespace-pre-wrap break-words text-base text-ink-2">{e.note}</p>}
              </div>
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
