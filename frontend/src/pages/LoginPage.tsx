import { AlertTriangle, ChevronDown, Headphones, LogIn } from 'lucide-react'
import { FormEvent, useState } from 'react'
import { useEngineStore } from '../stores/engineStore'

// Fase 2 (cierre del gap de Fase 1): antes de esto el frontend nunca hacía login — el WS real
// exige un token de sesión (ADR-0008/NFR-04) que solo `POST /auth/login` puede emitir. `App.tsx`
// muestra esta pantalla en vez de las rutas normales mientras no haya `authToken`.
export default function LoginPage() {
  const { userName, authError, authenticating, bridgeUrl, login, updateSettings } = useEngineStore()
  const [supervisorId, setSupervisorId] = useState(userName)
  const [passphrase, setPassphrase] = useState('')
  const [url, setUrl] = useState(bridgeUrl)
  const [showAdvanced, setShowAdvanced] = useState(false)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (url.trim() !== bridgeUrl) updateSettings(url.trim(), supervisorId.trim())
    login(supervisorId.trim(), passphrase)
  }

  return (
    <div className="login-screen">
      <form className="panel login-card" onSubmit={submit}>
        <div className="dispatcher-outline"><Headphones size={35} /></div>
        <h1>SIG Agent</h1>
        <p>Sign in with your supervisor credentials to start a training session.</p>

        {authError && <div className="call-notice error login-error"><AlertTriangle size={16} /><span>{authError}</span></div>}

        <label>
          <span>Supervisor name</span>
          <input value={supervisorId} onChange={(event) => setSupervisorId(event.target.value)} required autoFocus />
        </label>
        <label>
          <span>Passphrase</span>
          <input type="password" value={passphrase} onChange={(event) => setPassphrase(event.target.value)} required />
        </label>

        <button className="blue-button login-submit" type="submit" disabled={authenticating}>
          <LogIn size={17} />{authenticating ? 'Signing in…' : 'Sign in'}
        </button>

        <button type="button" className="text-link login-advanced-toggle" onClick={() => setShowAdvanced((value) => !value)}>
          <ChevronDown size={14} style={{ transform: showAdvanced ? 'rotate(180deg)' : undefined }} />Advanced
        </button>
        {showAdvanced && (
          <label>
            <span>Backend URL</span>
            <input value={url} onChange={(event) => setUrl(event.target.value)} pattern="wss?://.*" />
          </label>
        )}
      </form>
    </div>
  )
}
