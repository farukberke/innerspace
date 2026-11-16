import { useCallback, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { planApi } from '../../api/endpoints'
import type { Plan as PlanData, PlanContact, PlanContent } from '../../api/types'
import { Alert, Badge, Button, Card, formatDateTime, PageHeader, Spinner, TextArea, TextField } from '../../components/ui'
import { useLoad } from '../../hooks/useLoad'

const LIMITS = { items: 10, itemLength: 200, note: 500, contacts: 8 }

/** One item per line; blank lines are dropped (the backend rejects empty items). */
const toLines = (items: string[]) => items.join('\n')
const fromLines = (text: string) =>
  text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)

export function PlanForm({ plan, onSaved }: { plan: PlanContent; onSaved: (p: PlanData) => void }) {
  const [steps, setSteps] = useState(toLines(plan.moment_steps))
  const [note, setNote] = useState(plan.self_note)
  const [contacts, setContacts] = useState<PlanContact[]>(plan.contacts)
  const [signs, setSigns] = useState(toLines(plan.warning_signs))
  const [coping, setCoping] = useState(toLines(plan.coping_strategies))
  const [talk, setTalk] = useState(toLines(plan.talk_to_clinician))
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)

  const setContact = (i: number, patch: Partial<PlanContact>) =>
    setContacts((cs) => cs.map((c, j) => (j === i ? { ...c, ...patch } : c)))

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setSaved(false)
    try {
      const body: PlanContent = {
        moment_steps: fromLines(steps),
        self_note: note.trim(),
        contacts: contacts.filter((c) => c.name.trim() || c.phone.trim()).map((c) => ({ name: c.name.trim(), phone: c.phone.trim() })),
        warning_signs: fromLines(signs),
        coping_strategies: fromLines(coping),
        talk_to_clinician: fromLines(talk),
      }
      onSaved(await planApi.save(body))
      setSaved(true)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const listHint = `Her satıra bir madde (en fazla ${LIMITS.items} madde, her biri en fazla ${LIMITS.itemLength} karakter).`
  return (
    <form onSubmit={submit} className="space-y-5" aria-label="Planımı düzenle">
      {error && <Alert>{error}</Alert>}
      {saved && <Alert kind="success">Planın kaydedildi.</Alert>}
      <TextArea label="O an ne yapacağım? (adımlar)" hint={listHint} rows={5} value={steps} onChange={(e) => setSteps(e.target.value)} />
      <TextArea label="Kendime not" hint={`En fazla ${LIMITS.note} karakter.`} maxLength={LIMITS.note} rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
      <fieldset className="space-y-3">
        <legend className="text-sm font-medium text-slate-700">Arayabileceğim kişiler</legend>
        {contacts.map((c, i) => (
          <div key={i} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <TextField label={`Kişi ${i + 1} adı`} maxLength={80} value={c.name} onChange={(e) => setContact(i, { name: e.target.value })} />
            <TextField label={`Kişi ${i + 1} telefonu`} type="tel" maxLength={32} value={c.phone} onChange={(e) => setContact(i, { phone: e.target.value })} />
            <Button variant="secondary" onClick={() => setContacts((cs) => cs.filter((_, j) => j !== i))}>
              Kaldır
            </Button>
          </div>
        ))}
        {contacts.length < LIMITS.contacts && (
          <Button variant="secondary" onClick={() => setContacts((cs) => [...cs, { name: '', phone: '' }])}>
            Kişi ekle
          </Button>
        )}
      </fieldset>
      <TextArea label="Uyarı işaretlerim" hint={listHint} rows={4} value={signs} onChange={(e) => setSigns(e.target.value)} />
      <TextArea label="Bana iyi gelen başa çıkma yolları" hint={listHint} rows={4} value={coping} onChange={(e) => setCoping(e.target.value)} />
      <TextArea label="Uzmanımla konuşacaklarım" hint={listHint} rows={4} value={talk} onChange={(e) => setTalk(e.target.value)} />
      <Button type="submit" disabled={busy}>
        {busy ? 'Kaydediliyor…' : 'Planı kaydet'}
      </Button>
    </form>
  )
}

export function Plan() {
  const load = useCallback(() => planApi.get(), [])
  const { data, error, loading } = useLoad(load)
  const [override, setOverride] = useState<PlanData | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const plan = override ?? data

  async function setShared(share: boolean) {
    setActionError(null)
    try {
      setOverride(await (share ? planApi.share() : planApi.unshare()))
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }

  if (loading) return <Spinner />
  if (!plan) return <Alert>{error ?? 'Plan yüklenemedi.'}</Alert>

  return (
    <div className="space-y-5">
      <PageHeader
        title="Planım"
        actions={
          <Link to="/client/moment" className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:bg-slate-50">
            “O an” kartını aç
          </Link>
        }
      />
      <Alert kind="info">
        Bu plan senin. Zor bir an gelmeden önce, mümkünse uzmanınla birlikte hazırlamak iyi olur: taslağı yaz, bir sonraki seansa getir ve birlikte gözden geçirin.
      </Alert>
      {actionError && <Alert>{actionError}</Alert>}
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-medium text-slate-900">Uzmanınla paylaşım</h2>
            <p className="mt-1 text-sm text-slate-600">
              {plan.shared_at
                ? `Atanmış uzmanın planını salt okunur görebiliyor (${formatDateTime(plan.shared_at)}). İstediğin an geri alabilirsin.`
                : 'Plan şu an yalnızca sana görünür. İstersen atanmış uzmanınla salt okunur paylaşabilirsin.'}
            </p>
          </div>
          {plan.shared_at ? (
            <div className="flex items-center gap-2">
              <Badge tone="green">Paylaşıldı</Badge>
              <Button variant="secondary" onClick={() => setShared(false)}>
                Paylaşımı geri al
              </Button>
            </div>
          ) : (
            <Button onClick={() => setShared(true)} disabled={plan.updated_at === null}>
              Uzmanımla paylaş
            </Button>
          )}
        </div>
        {plan.updated_at === null && <p className="mt-2 text-xs text-slate-500">Paylaşmak için önce planını kaydet.</p>}
      </Card>
      <Card>
        <PlanForm plan={plan} onSaved={setOverride} />
      </Card>
    </div>
  )
}
