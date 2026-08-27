import { AlertTriangle, AudioLines, Headphones, Mic, Pause, PhoneOff, Play, ShieldCheck, Volume2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'motion/react'
import Header from '../components/Header'
import InCallLocationPanel from '../components/InCallLocationPanel'
import InCallVideoPanel from '../components/InCallVideoPanel'
import PreCallLocationBriefing from '../components/PreCallLocationBriefing'
import PreCallVideoGate from '../components/PreCallVideoGate'
import Waveform from '../components/Waveform'
import { getScenario, httpBaseFrom } from '../lib/api'
import { useEngineStore } from '../stores/engineStore'

export default function CallPage() {
  const navigate = useNavigate()
  const [seconds, setSeconds] = useState(0)
  const {
    connection, callStatus, dispatcherSpeaking, operatorSpeaking, recording,
    activeScenario, transcript, lastSession, error, warning, engineActivity,
    toggleRecording, pause, resume, endCall, clearNotice,
    scenarios, selectedScenarioId, bridgeUrl, authToken, videoAccess, videoAccessLoading,
    loadVideoAccess, notifyVideoEnded, clearVideoAccess, startCall,
    locationBrief, locationBriefLoading, loadLocationBrief, clearLocationBrief,
  } = useEngineStore()
  const [locationBriefingText, setLocationBriefingText] = useState('')

  // Escenarios de video (docs/designs/escenarios-de-video.md) + ubicación del incidente
  // (docs/designs/ubicacion-del-incidente.md): un solo lugar decide cuándo se manda
  // `call.start` — ni HomePage.tsx ni ScenariosPage.tsx lo hacen más (hallazgo de diseño #1).
  // `gateResolved` es "ya sabemos qué gates hay que mostrar, o ninguno" — antes de saberlo no se
  // manda `call.start` ni se muestra nada, para no parpadear entre estados. Los dos fetches
  // corren en PARALELO (`Promise.all`, hallazgo F14/B11 de las revisiones de diseño/ingeniería:
  // secuenciarlos duplicaría la latencia de pre-llamada sin necesidad). Orden de la secuencia,
  // decidido en Fase 2 Pass 7: ubicación (contexto de la escena) primero, video (evidencia del
  // incidente) segundo — cada `*GateDismissed` es distinto de "el dato dejó de existir": el
  // store SIGUE con `videoAccess`/`locationBrief` de esta sesión durante toda la llamada a
  // propósito (acceso opt-in en vivo, ver InCallVideoPanel.tsx/InCallLocationPanel.tsx), solo
  // dejan de mostrarse pantalla completa una vez que el entrenando continúa.
  const [gateResolved, setGateResolved] = useState(false)
  const [locationGateDismissed, setLocationGateDismissed] = useState(false)
  const [videoGateDismissed, setVideoGateDismissed] = useState(false)
  const selectedScenario = scenarios.find((scenario) => scenario.id === selectedScenarioId)

  useEffect(() => {
    // `gateResolved` es estado de ESTE montaje de CallPage (se resetea solo — cada llamada
    // nueva navega away y de vuelta, remontando el componente) — no depende de `callStatus`,
    // que después de completar una llamada queda en `"completed"`, no vuelve a `"idle"` por sí
    // solo (`startCall()` lo pisa directo a `"connecting"` la próxima vez).
    if (gateResolved) return

    let cancelled = false
    ;(async () => {
      const fetchLocation = selectedScenario?.has_location
        ? loadLocationBrief(selectedScenarioId)
        : Promise.resolve(clearLocationBrief()).then(() => null)
      const fetchVideo = selectedScenario?.has_video
        ? loadVideoAccess(selectedScenarioId)
        : Promise.resolve(clearVideoAccess()).then(() => null)
      // Cherry-pick de bajo costo del design doc (Fase 1 0D #2) — el briefing completo solo
      // hace falta cuando el gate de ubicación se va a mostrar; en paralelo con los otros dos
      // fetches, nunca los bloquea (si falla, el gate igual se muestra sin briefing, ver
      // PreCallLocationBriefing.tsx: la sección es opcional).
      const fetchBriefing = selectedScenario?.has_location && authToken
        ? getScenario(httpBaseFrom(bridgeUrl), authToken, selectedScenarioId).then((s) => s.briefing).catch(() => '')
        : Promise.resolve('')
      const [locationResult, videoResult, briefingResult] = await Promise.all([fetchLocation, fetchVideo, fetchBriefing])
      if (cancelled) return
      setLocationBriefingText(briefingResult)
      setGateResolved(true)
      // Ni ubicación ni video que mostrar — seguir directo al flujo de hoy, sin cambio de
      // comportamiento para escenarios sin ninguno de los dos configurados.
      if (!locationResult && !videoResult) startCall()
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedScenarioId])

  // Único punto de disparo de `call.start` desde el gate de ubicación — la ÚNICA condición
  // terminal es "no queda ningún gate de video pendiente", nunca un doble-fire: si hay video,
  // el gate de video es quien manda `call.start` a continuación (ver su propio onStartCall).
  const continueFromLocationGate = () => {
    setLocationGateDismissed(true)
    if (!videoAccess) startCall()
  }

  useEffect(() => {
    if (callStatus !== 'connected') return
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000)
    return () => window.clearInterval(timer)
  }, [callStatus])

  useEffect(() => {
    if (lastSession?.status === 'completed') navigate('/review')
  }, [lastSession, navigate])

  if (locationBrief && !locationGateDismissed) {
    return (
      <PreCallLocationBriefing
        scenarioTitle={selectedScenario?.title ?? 'Training Session'}
        location={locationBrief}
        briefing={locationBriefingText}
        isLastStep={!videoAccess}
        onContinue={continueFromLocationGate}
      />
    )
  }

  if (videoAccess && !videoGateDismissed) {
    return (
      <PreCallVideoGate
        scenarioTitle={selectedScenario?.title ?? 'Training Session'}
        streamUrl={`${httpBaseFrom(bridgeUrl)}${videoAccess.stream_url}`}
        onVideoEnded={() => notifyVideoEnded(selectedScenarioId)}
        onStartCall={() => { setVideoGateDismissed(true); startCall() }}
      />
    )
  }

  if (!gateResolved || videoAccessLoading || locationBriefLoading) {
    // Sin precedente de loading-state para media en este código (hallazgo de diseño #3) — un
    // spinner real sobre el mismo layout de siempre, nunca una pantalla en blanco que se lea
    // como colgada.
    return (
      <div className="call-screen">
        <Header center={<div className="session-live"><AudioLines size={22} /><strong>{selectedScenario?.title ?? 'Training Session'}</strong></div>} />
        <main className="call-main"><section className="call-card panel"><p className="empty-copy">Preparing your session…</p></section></main>
      </div>
    )
  }

  const time = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
  const connecting = callStatus === 'connecting'
  const processing = callStatus === 'processing'
  const paused = callStatus === 'paused'
  const statusLabel = connection !== 'connected' ? 'Waiting for engine' : connecting ? 'Connecting…' : processing ? 'Processing speech' : paused ? 'Paused' : callStatus === 'connected' ? 'Connected' : 'Connecting'
  const latestDispatcher = [...transcript].reverse().find((entry) => entry.role === 'dispatcher')?.text
  // Roadmap Fase 2 (pulido del loop en vivo): una caída de red a mitad de llamada no manda un
  // `error` event (la conexión ya está muerta) — se detecta por el propio estado de conexión.
  // La sesión igual queda registrada server-side como `network_drop`, sin puntaje punitivo
  // (ver `core/scoring.py`); esto solo avisa en vivo que pasó.
  const connectionLost = connection === 'disconnected' && Boolean(activeScenario) && callStatus !== 'completed'

  return (
    <div className="call-screen">
      <Header center={<div className="session-live"><AudioLines size={22} /><strong>{activeScenario?.title ?? 'Training Session'}</strong><i className={`status-dot ${connection === 'connected' ? 'success' : 'warning'}`} /><span>{connection}</span></div>} />
      <main className="call-main">
        <section className="call-card panel">
          {connectionLost && <div className="call-notice error"><AlertTriangle size={18} /><span>Connection to the server was lost — reconnecting. This session won't be scored.</span></div>}
          {!connectionLost && (error || warning) && <div className={`call-notice ${error ? 'error' : 'warning'}`}><AlertTriangle size={18} /><span>{error ?? warning}</span><button onClick={clearNotice}>×</button></div>}
          <motion.div className="call-avatar" animate={{ boxShadow: dispatcherSpeaking ? ['0 0 0 0 rgba(45,134,255,.1)','0 0 0 24px rgba(45,134,255,0)','0 0 0 0 rgba(45,134,255,.1)'] : '0 0 0 0 transparent' }} transition={{ duration: 2, repeat: Infinity }}>
            <Headphones size={54} strokeWidth={1.7} />
            <ShieldCheck size={20} className="avatar-badge" />
          </motion.div>
          <h1>911 Dispatch</h1>
          <div className="connected-label"><i className={`status-dot ${callStatus === 'connected' ? 'success' : 'warning'}`} />{statusLabel}</div>
          <div className="call-timer">{time}</div>
          <Waveform active={dispatcherSpeaking || operatorSpeaking || processing} />
          <div className="speaking-pill"><AudioLines size={23} />{engineActivity ?? (processing ? 'Transcribing and preparing response…' : operatorSpeaking ? 'Listening to you…' : dispatcherSpeaking ? 'Dispatcher speaking…' : 'Ready for your response')}</div>
          {latestDispatcher && <p className="latest-prompt" aria-live="polite">{latestDispatcher}</p>}
          <div className="live-indicators">
            <span><span className={`circle-icon ${recording ? 'recording' : ''}`}><Mic size={22} /></span>{recording ? 'Recording' : 'Mic Ready'}</span>
            <em />
            <span><span className="circle-icon"><Volume2 size={22} /></span>{dispatcherSpeaking ? 'Playing' : 'Speaker On'}</span>
          </div>
        </section>
      </main>
      <footer className="call-controls functional-controls">
        <button className="secondary-button" disabled={processing || connection !== 'connected'} onClick={paused ? resume : pause}>{paused ? <Play size={18} /> : <Pause size={18} />}{paused ? 'Resume Simulation' : 'Pause Simulation'}</button>
        <button className={`record-button ${recording ? 'active' : ''}`} disabled={processing || paused || dispatcherSpeaking || callStatus !== 'connected'} onClick={toggleRecording}><Mic size={24} />{recording ? 'Stop & Send' : dispatcherSpeaking ? 'Wait for Dispatcher' : 'Hold to Speak'}</button>
        <div className="device connection"><AudioLines size={28} /><div><strong>Voice Engine</strong><span className={connection === 'connected' ? 'success-text' : ''}><i className={`status-dot ${connection === 'connected' ? 'success' : 'warning'}`} />{connection}</span></div></div>
        <button className="danger-button" disabled={!['connected', 'paused', 'processing'].includes(callStatus)} onClick={endCall}><PhoneOff size={22} />End Call</button>
      </footer>

      {/* Pedido explícito del usuario: opción de ver el video DURANTE la llamada, no solo
          antes. Cerrado por default a propósito (ver InCallVideoPanel.tsx) — el entrenando lo
          abre si lo necesita, no se le pone en pantalla sin pedirlo. */}
      {videoAccess && <InCallVideoPanel streamUrl={`${httpBaseFrom(bridgeUrl)}${videoAccess.stream_url}`} />}
      {/* Mismo patrón, mismo razonamiento — ubicación del incidente (F12, corrección de la voz
          de diseño independiente sobre el design doc). */}
      {locationBrief && <InCallLocationPanel location={locationBrief} />}
    </div>
  )
}
