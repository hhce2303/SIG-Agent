import { AlertTriangle, AudioLines, Headphones, Mic, Pause, PhoneOff, Play, ShieldCheck, Volume2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'motion/react'
import Header from '../components/Header'
import Waveform from '../components/Waveform'
import { useEngineStore } from '../stores/engineStore'

export default function CallPage() {
  const navigate = useNavigate()
  const [seconds, setSeconds] = useState(0)
  const {
    connection, callStatus, dispatcherSpeaking, operatorSpeaking, recording,
    activeScenario, transcript, lastSession, error, warning, engineActivity,
    toggleRecording, pause, resume, endCall, clearNotice,
  } = useEngineStore()

  useEffect(() => {
    if (callStatus !== 'connected') return
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000)
    return () => window.clearInterval(timer)
  }, [callStatus])

  useEffect(() => {
    if (lastSession?.status === 'completed') navigate('/review')
  }, [lastSession, navigate])

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
    </div>
  )
}
