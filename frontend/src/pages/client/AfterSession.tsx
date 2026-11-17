import { useCallback, useState, type FormEvent } from 'react'
import { errorMessage } from '../../api/client'
import { afterSessionApi } from '../../api/endpoints'
import type { AfterSessionNote, CrisisInfo } from '../../api/types'
import { AiDisclaimer } from '../../components/AiDisclaimer'
import { CrisisScreen } from '../../components/CrisisScreen'
import { Alert, Button, Card, Empty, formatDateTime, PageHeader, Spinner, TextArea } from '../../components/ui'
import { useLoad } from '../../hooks/useLoad'

function isCrisis(r: AfterSessionNote | CrisisInfo): r is CrisisInfo {
  return 'crisis' in r && r.crisis === true
}

function Section({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null
  return (
    <div className="mt-3">
      <h3 className="text-base font-semibold text-ink-2">{title}</h3>
      <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-ink-2">
        {items.map((t, i) => (
          <li key={i} className="break-words">
            {t}
          </li>
        ))}
      </ul>
    </div>
  )
}

export function AfterSession() {
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [crisis, setCrisis] = useState<CrisisInfo | null>(null)
  const [busy, setBusy] = useState(false)
  const load = useCallback(() => afterSessionApi.list(), [])
  const { data, error: loadError, loading, reload } = useLoad(load)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await afterSessionApi.create(text)
      if (isCrisis(res)) {
        setCrisis(res)
      } else {
        setText('')
        reload()
      }
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHeader title="Seans sonrası notları" />
      {crisis ? (
        <div className="mb-5">
          <CrisisScreen crisis={crisis} onClose={() => setCrisis(null)} />
        </div>
      ) : (
        <Card className="mb-5">
          <form onSubmit={submit} className="space-y-4" aria-label="Seans sonrası notu">
            {error && <Alert>{error}</Alert>}
            <TextArea
              label="Seans nasıldı? Kendi sözlerinle yaz."
              hint="Not, “konuştuklarımız / deneyeceklerim / sonraki seansa sorularım” olarak düzenlenir."
              required
              maxLength={5000}
              rows={6}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <Button type="submit" disabled={busy || !text.trim()}>
              {busy ? 'Düzenleniyor…' : 'Notu düzenle ve kaydet'}
            </Button>
          </form>
        </Card>
      )}
      {loadError && <Alert>{loadError}</Alert>}
      {loading ? (
        <Spinner />
      ) : data && data.length === 0 ? (
        <Empty title="Henüz seans sonrası notun yok.">Seanstan çıkınca aklında kalanı iki dakikada yaz: konuştuklarınız, denemek istediklerin, sonraki seansa soruların. AI yalnızca bu üç başlığa ayırır.</Empty>
      ) : (
        <ul className="space-y-3">
          {data?.map((n) => (
            <li key={n.id}>
              <Card>
                <p className="text-xs text-muted">{formatDateTime(n.created_at)}</p>
                <Section title="Konuştuklarımız" items={n.discussed} />
                <Section title="Deneyeceklerim" items={n.to_try} />
                <Section title="Sonraki seansa sorularım" items={n.questions} />
                <div className="mt-3">
                  <AiDisclaimer audience="client" kind="note" />
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
