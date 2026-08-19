import { CheckCircle2, RefreshCw, Save } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import { useEngineStore } from '../stores/engineStore'

export default function SettingsPage() {
  const { bridgeUrl, userName, connection, engineVersion, updateSettings } = useEngineStore()
  const [url, setUrl] = useState(bridgeUrl)
  const [name, setName] = useState(userName)
  const [saved, setSaved] = useState(false)
  useEffect(() => setSaved(false), [url, name])
  const submit = (event: FormEvent) => {
    event.preventDefault()
    updateSettings(url.trim(), name.trim())
    setSaved(true)
  }
  return <AppShell active="Settings"><div className="content-page settings-page"><div className="page-heading-row"><div><h1>Settings</h1><p>Frontend and backend connection settings.</p></div></div><form className="panel settings-form" onSubmit={submit}><div className="settings-status"><div><i className={`status-dot ${connection === 'connected' ? 'success' : 'warning'}`} /><strong>Backend: {connection}</strong></div><span>Protocol version {engineVersion || 'not detected'}</span></div><label><span>Operator name</span><input value={name} onChange={(event) => setName(event.target.value)} required /></label><label><span>Backend WebSocket URL</span><input value={url} onChange={(event) => setUrl(event.target.value)} type="url" required pattern="wss?://.*" /></label><p className="form-help">Secrets and AI provider keys belong exclusively to the backend and must never use a `VITE_` variable.</p><div className="page-actions"><button type="button" className="secondary-button" onClick={() => updateSettings(url.trim(), name.trim())}><RefreshCw size={17} />Reconnect</button><button className="blue-button" type="submit"><Save size={17} />Save settings</button>{saved && <span className="saved-label"><CheckCircle2 size={16} />Saved locally</span>}</div></form></div></AppShell>
}
