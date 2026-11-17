import { useState, type FormEvent } from 'react'
import { errorMessage } from '../../api/client'
import { entriesApi } from '../../api/endpoints'
import type { Entry, EntryInput, EntryKind } from '../../api/types'
import { Alert, Button, CheckField, SelectField, TextArea, TextField } from '../../components/ui'

export const KIND_LABEL: Record<EntryKind, string> = {
  quick: 'Günlük',
  panic: 'Panik atağı',
  medication: 'İlaç',
  avoidance: 'Kaçınma',
}

export function toLocalInput(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const splitList = (s: string): string[] =>
  s
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)

const num = (v: unknown): string => (typeof v === 'number' ? String(v) : '')
const str = (v: unknown): string => (typeof v === 'string' ? v : '')
const list = (v: unknown): string => (Array.isArray(v) ? v.join(', ') : '')

/** Builds the kind-specific `details` object the backend validates (extra keys are rejected). */
export function buildDetails(kind: EntryKind, f: Record<string, string | boolean>): Record<string, unknown> {
  const optInt = (v: string | boolean) => (typeof v === 'string' && v !== '' ? Number(v) : null)
  switch (kind) {
    case 'quick': {
      const d: Record<string, unknown> = {}
      const mood = optInt(f.mood)
      if (mood !== null) d.mood = mood
      const sleep = optInt(f.sleep)
      if (sleep !== null) d.sleep_hours = sleep
      return d
    }
    case 'panic': {
      const d: Record<string, unknown> = { intensity: Number(f.intensity), symptoms: splitList(String(f.symptoms)) }
      const dur = optInt(f.duration)
      if (dur !== null) d.duration_minutes = dur
      if (String(f.trigger).trim()) d.trigger = String(f.trigger).trim()
      return d
    }
    case 'medication':
      return { medication_name: String(f.medication_name).trim(), taken: Boolean(f.taken), side_effects: splitList(String(f.side_effects)) }
    case 'avoidance': {
      const d: Record<string, unknown> = { situation: String(f.situation).trim(), avoided: Boolean(f.avoided) }
      const a = optInt(f.anxiety)
      if (a !== null) d.anxiety = a
      return d
    }
  }
}

export function EntryForm({ entry, onSaved, onCancel }: { entry?: Entry; onSaved: () => void; onCancel: () => void }) {
  const d = entry?.details ?? {}
  const [kind, setKind] = useState<EntryKind>(entry?.kind ?? 'quick')
  const [occurredAt, setOccurredAt] = useState(toLocalInput(entry?.occurred_at ?? new Date().toISOString()))
  const [note, setNote] = useState(entry?.note ?? '')
  const [f, setF] = useState<Record<string, string | boolean>>({
    mood: num(d.mood),
    sleep: num(d.sleep_hours),
    intensity: num(d.intensity) || '5',
    duration: num(d.duration_minutes),
    symptoms: list(d.symptoms),
    trigger: str(d.trigger),
    medication_name: str(d.medication_name),
    taken: d.taken === undefined ? true : Boolean(d.taken),
    side_effects: list(d.side_effects),
    situation: str(d.situation),
    avoided: Boolean(d.avoided),
    anxiety: num(d.anxiety),
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const set = (k: string, v: string | boolean) => setF((p) => ({ ...p, [k]: v }))

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const body: EntryInput = {
      kind,
      occurred_at: new Date(occurredAt).toISOString(),
      note: note.trim() || null,
      details: buildDetails(kind, f),
    }
    try {
      if (entry) await entriesApi.update(entry.id, { occurred_at: body.occurred_at, note: body.note, details: body.details })
      else await entriesApi.create(body)
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" aria-label={entry ? 'Kaydı düzenle' : 'Yeni kayıt'}>
      {error && <Alert>{error}</Alert>}
      <div className="grid gap-4 sm:grid-cols-2">
        <SelectField label="Kayıt türü" value={kind} disabled={!!entry} onChange={(e) => setKind(e.target.value as EntryKind)}>
          {(Object.keys(KIND_LABEL) as EntryKind[]).map((k) => (
            <option key={k} value={k}>
              {KIND_LABEL[k]}
            </option>
          ))}
        </SelectField>
        <TextField label="Ne zaman oldu?" type="datetime-local" required value={occurredAt} onChange={(e) => setOccurredAt(e.target.value)} />
      </div>

      {kind === 'quick' && (
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Ruh hali (1-5, isteğe bağlı)" type="number" min={1} max={5} value={String(f.mood)} onChange={(e) => set('mood', e.target.value)} />
          <TextField
            label="Dün gece uyku (saat, isteğe bağlı)"
            type="number"
            inputMode="decimal"
            min={0}
            max={24}
            step={0.5}
            value={String(f.sleep)}
            onChange={(e) => set('sleep', e.target.value)}
          />
        </div>
      )}
      {kind === 'panic' && (
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Şiddet (0-10)" type="number" min={0} max={10} required value={String(f.intensity)} onChange={(e) => set('intensity', e.target.value)} />
          <TextField label="Süre (dakika)" type="number" min={0} max={1440} value={String(f.duration)} onChange={(e) => set('duration', e.target.value)} />
          <TextField label="Belirtiler" hint="Virgülle ayır." value={String(f.symptoms)} onChange={(e) => set('symptoms', e.target.value)} />
          <TextField label="Tetikleyici" maxLength={200} value={String(f.trigger)} onChange={(e) => set('trigger', e.target.value)} />
        </div>
      )}
      {kind === 'medication' && (
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="İlaç adı" required maxLength={200} value={String(f.medication_name)} onChange={(e) => set('medication_name', e.target.value)} />
          <TextField label="Yan etkiler" hint="Virgülle ayır." value={String(f.side_effects)} onChange={(e) => set('side_effects', e.target.value)} />
          <CheckField label="İlacı aldım" checked={Boolean(f.taken)} onChange={(e) => set('taken', e.target.checked)} />
        </div>
      )}
      {kind === 'avoidance' && (
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Durum" required maxLength={200} value={String(f.situation)} onChange={(e) => set('situation', e.target.value)} />
          <TextField label="Kaygı (0-10)" type="number" min={0} max={10} value={String(f.anxiety)} onChange={(e) => set('anxiety', e.target.value)} />
          <CheckField label="Kaçındım" checked={Boolean(f.avoided)} onChange={(e) => set('avoided', e.target.checked)} />
        </div>
      )}

      <TextArea
        label={kind === 'quick' ? 'Not' : 'Not (isteğe bağlı)'}
        required={kind === 'quick'}
        maxLength={5000}
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <div className="flex gap-2">
        <Button type="submit" disabled={busy}>
          {busy ? 'Kaydediliyor…' : 'Kaydet'}
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          Vazgeç
        </Button>
      </div>
    </form>
  )
}
