import { useCallback, useState, type FormEvent } from 'react'
import { errorMessage } from '../../api/client'
import { adminApi } from '../../api/endpoints'
import type { UserRole } from '../../api/types'
import { ROLE_LABEL } from '../../auth/roles'
import { useAuth } from '../../auth/AuthContext'
import { Alert, Badge, Button, Card, Empty, formatDate, PageHeader, SelectField, Spinner } from '../../components/ui'
import { useLoad } from '../../hooks/useLoad'
import { InviteForm } from '../InviteForm'

export function AdminUsers() {
  const { state } = useAuth()
  const selfId = state.status === 'authed' ? state.user.id : null
  const [role, setRole] = useState<UserRole | ''>('')
  const [inviting, setInviting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const load = useCallback(() => adminApi.users(role || undefined), [role])
  const { data, error, loading, reload } = useLoad(load)
  const clinicians = useLoad(useCallback(() => adminApi.users('clinician'), []))

  async function toggle(id: string, active: boolean) {
    try {
      await adminApi.setActive(id, active)
      setActionError(null)
      reload()
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }

  return (
    <div>
      <PageHeader title="Kullanıcılar" actions={<Button onClick={() => setInviting((i) => !i)}>{inviting ? 'Kapat' : 'Davet et'}</Button>} />
      {inviting && (
        <div className="mb-5">
          <InviteForm
            roles={['clinician', 'client']}
            clinicians={clinicians.data?.filter((c) => c.is_active)}
            onCreated={reload}
          />
        </div>
      )}
      <div className="mb-4 max-w-xs">
        <SelectField label="Role göre filtrele" value={role} onChange={(e) => setRole(e.target.value as UserRole | '')}>
          <option value="">Tümü</option>
          <option value="clinician">Uzman</option>
          <option value="client">Danışan</option>
          <option value="org_admin">Klinik yöneticisi</option>
        </SelectField>
      </div>
      {(error || actionError) && <Alert>{error ?? actionError}</Alert>}
      {loading ? (
        <Spinner />
      ) : data && data.length === 0 ? (
        <Empty>Kullanıcı bulunamadı.</Empty>
      ) : (
        <ul className="space-y-3">
          {data?.map((u) => (
            <li key={u.id}>
              <Card>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{u.display_name}</p>
                    <p className="truncate text-xs text-slate-500">{u.email}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone="indigo">{ROLE_LABEL[u.role]}</Badge>
                    <Badge tone={u.is_active ? 'green' : 'slate'}>{u.is_active ? 'Aktif' : 'Pasif'}</Badge>
                    {u.id !== selfId && (
                      <Button variant="secondary" onClick={() => toggle(u.id, !u.is_active)}>
                        {u.is_active ? 'Pasifleştir' : 'Aktifleştir'}
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function AdminAssignments() {
  const [clinicianId, setClinicianId] = useState('')
  const [clientId, setClientId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const assignments = useLoad(useCallback(() => adminApi.assignments(), []))
  const users = useLoad(useCallback(() => adminApi.users(), []))
  const active = (r: UserRole) => users.data?.filter((u) => u.role === r && u.is_active) ?? []
  const names = new Map(users.data?.map((u) => [u.id, u.display_name]))

  async function create(e: FormEvent) {
    e.preventDefault()
    try {
      await adminApi.createAssignment(clinicianId, clientId)
      setError(null)
      setClientId('')
      assignments.reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  async function remove(id: string) {
    if (!window.confirm('Bu atamayı silmek istediğine emin misin?')) return
    try {
      await adminApi.deleteAssignment(id)
      setError(null)
      assignments.reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <div>
      <PageHeader title="Atamalar" />
      <Card className="mb-5">
        <form onSubmit={create} className="space-y-4" aria-label="Yeni atama">
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectField label="Uzman" required value={clinicianId} onChange={(e) => setClinicianId(e.target.value)}>
              <option value="">Seç…</option>
              {active('clinician').map((u) => (
                <option key={u.id} value={u.id}>
                  {u.display_name}
                </option>
              ))}
            </SelectField>
            <SelectField label="Danışan" required value={clientId} onChange={(e) => setClientId(e.target.value)}>
              <option value="">Seç…</option>
              {active('client').map((u) => (
                <option key={u.id} value={u.id}>
                  {u.display_name}
                </option>
              ))}
            </SelectField>
          </div>
          <Button type="submit" disabled={!clinicianId || !clientId}>
            Atama oluştur
          </Button>
        </form>
      </Card>
      {(error || assignments.error) && <Alert>{error ?? assignments.error}</Alert>}
      {assignments.loading ? (
        <Spinner />
      ) : assignments.data && assignments.data.length === 0 ? (
        <Empty>Henüz atama yok.</Empty>
      ) : (
        <ul className="space-y-3">
          {assignments.data?.map((a) => (
            <li key={a.id}>
              <Card>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm">
                    <span className="font-medium">{names.get(a.clinician_id) ?? 'Uzman'}</span> → {names.get(a.client_id) ?? 'Danışan'}
                    <span className="ml-2 text-xs text-slate-500">{formatDate(a.created_at)}</span>
                  </p>
                  <Button variant="ghost" onClick={() => remove(a.id)}>
                    Sil
                  </Button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
