import { useState, type FormEvent } from 'react'
import { errorMessage } from '../api/client'
import { invitationsApi } from '../api/endpoints'
import type { InvitationCreated, User, UserRole } from '../api/types'
import { Alert, Button, Card, formatDateTime, SelectField, TextField } from '../components/ui'

/** Creates an invitation. The one-time code is shown here (e-mail delivery is out of scope). */
export function InviteForm({
  roles,
  clinicians,
  onCreated,
}: {
  roles: UserRole[]
  clinicians?: User[]
  onCreated?: () => void
}) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<UserRole>(roles[0])
  const [clinicianId, setClinicianId] = useState('')
  const [result, setResult] = useState<InvitationCreated | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const inv = await invitationsApi.create(email.trim(), role, role === 'client' ? clinicianId : undefined)
      setResult(inv)
      setEmail('')
      onCreated?.()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <form onSubmit={submit} className="space-y-4" aria-label="Davet gönder">
        {error && <Alert>{error}</Alert>}
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Davet edilecek e-posta" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          {roles.length > 1 && (
            <SelectField label="Rol" value={role} onChange={(e) => setRole(e.target.value as UserRole)}>
              <option value="clinician">Uzman</option>
              <option value="client">Danışan</option>
            </SelectField>
          )}
          {clinicians && role === 'client' && (
            <SelectField label="Atanacak uzman (isteğe bağlı)" value={clinicianId} onChange={(e) => setClinicianId(e.target.value)}>
              <option value="">Şimdilik atama yapma</option>
              {clinicians.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.display_name}
                </option>
              ))}
            </SelectField>
          )}
        </div>
        <Button type="submit" disabled={busy}>
          {busy ? 'Oluşturuluyor…' : 'Davet oluştur'}
        </Button>
      </form>
      {result && (
        <div className="mt-4">
          <Alert kind="success">
            <p>
              {result.email} için davet oluşturuldu (son geçerlilik: {formatDateTime(result.expires_at)}). E-posta gönderilmiyor; aşağıdaki kodu
              kişiye ilet. Kod yalnızca bir kez gösterilir.
            </p>
            <p className="mt-2 break-all rounded bg-white px-3 py-2 font-mono text-xs text-ink" data-testid="invite-token">
              {result.token}
            </p>
          </Alert>
        </div>
      )}
    </Card>
  )
}
