import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, errorMessage } from '../api/client'
import { authApi } from '../api/endpoints'
import { Alert, Button, TextField } from '../components/ui'
import { AuthShell } from './Login'

export function AcceptInvitation() {
  const [token, setToken] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await authApi.acceptInvitation(token.trim(), password, name.trim())
      setDone(true)
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 400
          ? 'Davet geçersiz ya da süresi dolmuş. Yeni bir davet iste.'
          : errorMessage(err),
      )
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <AuthShell title="Hesabın hazır">
        <Alert kind="success">Hesabın oluşturuldu. Şimdi giriş yapabilirsin.</Alert>
        <Link to="/login" className="mt-4 block text-center font-medium text-indigo-700 underline">
          Giriş sayfasına git
        </Link>
      </AuthShell>
    )
  }

  return (
    <AuthShell title="Daveti kabul et">
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <TextField
          label="Davet kodu"
          hint="Seni davet eden kişinin verdiği kodu yapıştır."
          required
          autoComplete="off"
          value={token}
          onChange={(e) => setToken(e.target.value)}
        />
        <TextField label="Adın" required maxLength={120} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
        <TextField
          label="Parola"
          type="password"
          required
          minLength={12}
          maxLength={128}
          autoComplete="new-password"
          hint="En az 12 karakter."
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? 'Kaydediliyor…' : 'Hesabı oluştur'}
        </Button>
        <p className="text-center text-sm">
          <Link to="/login" className="text-indigo-700 underline">
            Giriş sayfasına dön
          </Link>
        </p>
      </form>
    </AuthShell>
  )
}
