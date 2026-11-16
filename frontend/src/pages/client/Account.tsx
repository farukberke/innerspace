import { useState, type FormEvent } from 'react'
import { useAuth } from '../../auth/AuthContext'
import { errorMessage } from '../../api/client'
import { accountApi } from '../../api/endpoints'
import { Alert, Button, Card, PageHeader, TextField } from '../../components/ui'

const CONFIRM_WORD = 'SİL'

/** Hesabım: data rights. Export is the caller's own data only; deletion is permanent. */
export function Account() {
  const { state, logout } = useAuth()
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [password, setPassword] = useState('')
  const [word, setWord] = useState('')
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  async function download() {
    setExporting(true)
    setExportError(null)
    try {
      const data = await accountApi.export()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'innerspace-verilerim.json'
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setExportError(errorMessage(err))
    } finally {
      setExporting(false)
    }
  }

  async function remove(e: FormEvent) {
    e.preventDefault()
    setDeleting(true)
    setDeleteError(null)
    try {
      await accountApi.remove(password)
      logout() // the account is gone: end the local session
    } catch (err) {
      setDeleteError(errorMessage(err))
      setDeleting(false)
    }
  }

  return (
    <div>
      <PageHeader title="Hesabım" />
      {state.status === 'authed' && (
        <p className="mb-4 text-sm text-ink-2">
          {state.user.display_name} · {state.user.email}
        </p>
      )}

      <section aria-labelledby="export-title" className="mb-5">
        <Card>
          <h2 id="export-title" className="text-base font-semibold text-ink">
            Verimi indir
          </h2>
          <p className="mt-1 text-sm text-ink-2">
            Kayıtların, özetlerin (konular ve dayandığı kayıtlarla), seans sonrası notların, planın, randevuların ve profil bilgilerin tek bir JSON dosyası olarak iner. Yalnızca senin verin.
          </p>
          {exportError && <Alert>{exportError}</Alert>}
          <div className="mt-3">
            <Button onClick={download} disabled={exporting}>
              {exporting ? 'Hazırlanıyor…' : 'Verimi indir'}
            </Button>
          </div>
        </Card>
      </section>

      <section aria-labelledby="delete-title">
        <Card className="border-danger-200">
          <h2 id="delete-title" className="text-base font-semibold text-danger-800">
            Hesabımı sil
          </h2>
          <p className="mt-1 text-sm text-ink-2">
            Hesabın ve tüm verilerin (kayıtlar, özetler, notlar, plan, randevular) kalıcı olarak silinir. Paylaştığın özetler uzmanının ekranından da kaybolur. Bu işlem geri alınamaz. İstersen önce verini indir.
          </p>
          {!confirming ? (
            <div className="mt-3">
              <Button variant="danger" onClick={() => setConfirming(true)}>
                Hesabımı silmek istiyorum
              </Button>
            </div>
          ) : (
            <form onSubmit={remove} className="mt-3 space-y-3" aria-label="Hesabı sil">
              {deleteError && <Alert>{deleteError}</Alert>}
              <TextField label="Parolan" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
              <TextField
                label={`Onaylamak için ${CONFIRM_WORD} yaz`}
                required
                autoComplete="off"
                value={word}
                onChange={(e) => setWord(e.target.value)}
              />
              <div className="flex gap-2">
                <Button type="submit" variant="danger" disabled={deleting || password === '' || word !== CONFIRM_WORD}>
                  {deleting ? 'Siliniyor…' : 'Hesabımı kalıcı olarak sil'}
                </Button>
                <Button variant="secondary" disabled={deleting} onClick={() => setConfirming(false)}>
                  Vazgeç
                </Button>
              </div>
            </form>
          )}
        </Card>
      </section>
    </div>
  )
}
