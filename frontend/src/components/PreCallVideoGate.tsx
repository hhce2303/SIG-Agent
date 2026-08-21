import { AlertTriangle, AudioLines, Headphones, Play, RotateCcw } from 'lucide-react'
import { useState } from 'react'
import Header from './Header'

// Escenarios de video — docs/designs/escenarios-de-video.md, hallazgos de diseño 1-4.
//
// Presentacional a propósito: `CallPage.tsx` es dueño de CUÁNDO se llama a este componente (un
// solo lugar decide, no HomePage.tsx/ScenariosPage.tsx por separado — hallazgo de diseño #1) y
// de qué pasa después (`onVideoEnded`/`onStartCall`). Este componente solo sabe reproducir un
// video y mostrar el interstitial de calma — nunca decide si `call.start` debe mandarse.
//
// Reglas de diseño que este componente encarna:
// - Pantalla completa, tema oscuro consistente con CallPage (nunca un reproductor "de app de
//   video" genérico bolted-on).
// - SIN auto-avance: terminar el video no arranca la llamada — el entrenando decide cuándo,
//   vía el interstitial de calma.
// - Permitir rebobinar/re-ver antes de llamar (`controls` nativo) — es práctica, no examen.
// - Error de reproducción: reintento + salida explícita "Skip video, start call", enmarcado
//   como un problema técnico, nunca como que el entrenando hizo algo mal.
export default function PreCallVideoGate({
  scenarioTitle,
  streamUrl,
  onVideoEnded,
  onStartCall,
}: {
  scenarioTitle: string
  streamUrl: string
  onVideoEnded: () => void
  onStartCall: () => void
}) {
  const [phase, setPhase] = useState<'watching' | 'ready'>('watching')
  const [videoError, setVideoError] = useState(false)
  const [retryKey, setRetryKey] = useState(0)

  const finishWatching = () => {
    onVideoEnded()
    setPhase('ready')
  }

  return (
    <div className="call-screen pre-call-video-gate">
      <Header center={<div className="session-live"><AudioLines size={22} /><strong>{scenarioTitle}</strong></div>} />
      <main className="call-main">
        <section className="call-card panel video-gate-card">
          {phase === 'watching' && (
            <>
              <p className="video-gate-eyebrow">Before you call it in</p>
              <h1>{scenarioTitle}</h1>
              <p className="video-gate-copy">Watch what happened, then report it to the dispatcher — just like a real call.</p>

              {videoError ? (
                <div className="call-notice error video-gate-error">
                  <AlertTriangle size={18} />
                  <span>The video couldn't be played. This is a technical issue, not something you did.</span>
                  <div className="video-gate-error-actions">
                    <button className="secondary-button" onClick={() => { setVideoError(false); setRetryKey((key) => key + 1) }}>
                      <RotateCcw size={16} />Try again
                    </button>
                    <button className="blue-button" onClick={finishWatching}>
                      <Play size={16} />Skip video, start call
                    </button>
                  </div>
                </div>
              ) : (
                <video
                  key={retryKey}
                  className="video-gate-player"
                  src={streamUrl}
                  controls
                  autoPlay
                  onEnded={finishWatching}
                  onError={() => setVideoError(true)}
                >
                  <track kind="captions" />
                </video>
              )}

              {!videoError && (
                <button className="secondary-button video-gate-skip" onClick={finishWatching}>
                  Skip video, start call
                </button>
              )}
            </>
          )}

          {phase === 'ready' && (
            <div className="video-gate-ready">
              <div className="call-avatar"><Headphones size={54} strokeWidth={1.7} /></div>
              <h1>Take a moment.</h1>
              <p className="video-gate-copy">When you're ready, call it in.</p>
              <button className="primary-cta" onClick={onStartCall}><Play fill="currentColor" size={22} />Start Call</button>
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
