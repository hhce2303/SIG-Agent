import { CheckCircle2, RefreshCw, Save } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import { getSettings, httpBaseFrom, updateTtsVoice } from '../lib/api'
import { useEngineStore } from '../stores/engineStore'

// Voces conocidas de Kokoro-82M (hexgrad/Kokoro-82M) — no es la lista exhaustiva del modelo,
// solo las opciones más comunes; el backend no valida contra un enum fijo (ver `settings`
// table), así que cualquier id de voz válido para el pipeline funciona igual.
const KNOWN_VOICES = ['am_michael', 'am_adam', 'af_bella', 'af_sarah', 'bf_emma', 'bm_george']

export default function SettingsPage() {
  const { bridgeUrl, userName, authToken, connection, engineVersion, updateSettings } = useEngineStore()
  const [url, setUrl] = useState(bridgeUrl)
  const [name, setName] = useState(userName)
  const [saved, setSaved] = useState(false)
  const [ttsVoice, setTtsVoice] = useState('')
  const [voiceSaved, setVoiceSaved] = useState(false)

  useEffect(() => setSaved(false), [url, name])

  useEffect(() => {
    if (!authToken) return
    getSettings(httpBaseFrom(bridgeUrl), authToken).then((body) => setTtsVoice(body.tts_voice)).catch(() => {})
  }, [authToken, bridgeUrl])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    updateSettings(url.trim(), name.trim())
    setSaved(true)
  }

  const saveVoice = async () => {
    if (!authToken || !ttsVoice) return
    await updateTtsVoice(httpBaseFrom(bridgeUrl), authToken, ttsVoice)
    setVoiceSaved(true)
    window.setTimeout(() => setVoiceSaved(false), 2000)
  }

  return (
    <AppShell active="Settings">
      <div className="content-page settings-page">
        <div className="page-heading-row"><div><h1>Settings</h1><p>Frontend and backend connection settings.</p></div></div>

        <form className="panel settings-form" onSubmit={submit}>
          <div className="settings-status">
            <div><i className={`status-dot ${connection === 'connected' ? 'success' : 'warning'}`} /><strong>Backend: {connection}</strong></div>
            <span>Protocol version {engineVersion || 'not detected'}</span>
          </div>
          <label><span>Operator name</span><input value={name} onChange={(event) => setName(event.target.value)} required /></label>
          <label><span>Backend WebSocket URL</span><input value={url} onChange={(event) => setUrl(event.target.value)} type="url" required pattern="wss?://.*" /></label>
          <p className="form-help">Secrets and AI provider keys belong exclusively to the backend and must never use a `VITE_` variable. Changing the backend URL signs you out.</p>
          <div className="page-actions">
            <button type="button" className="secondary-button" onClick={() => updateSettings(url.trim(), name.trim())}><RefreshCw size={17} />Reconnect</button>
            <button className="blue-button" type="submit"><Save size={17} />Save settings</button>
            {saved && <span className="saved-label"><CheckCircle2 size={16} />Saved locally</span>}
          </div>
        </form>

        {/* Roadmap Fase 2 (Ajustes): alcance mínimo a propósito — solo voz de TTS. No hay
            sensibilidad de VAD todavía porque no hay VAD automático implementado (ver ADR-0005). */}
        <div className="panel settings-form voice-settings-form">
          <label><span>Dispatcher voice (Kokoro TTS)</span>
            <select value={ttsVoice} onChange={(event) => setTtsVoice(event.target.value)}>
              {KNOWN_VOICES.map((voice) => <option key={voice} value={voice}>{voice}</option>)}
            </select>
          </label>
          <div className="page-actions">
            <button className="blue-button" type="button" onClick={saveVoice}><Save size={17} />Save voice</button>
            {voiceSaved && <span className="saved-label"><CheckCircle2 size={16} />Saved</span>}
          </div>
        </div>
      </div>
    </AppShell>
  )
}
