import { MapPin, Play } from 'lucide-react'
import Header from './Header'
import LocationMiniMap from './LocationMiniMap'
import type { ScenarioLocationAccess } from '../types'

// Ubicación del incidente — docs/designs/ubicacion-del-incidente.md, 0A punto 1 y Fase 2.
//
// Presentacional a propósito, mismo patrón que PreCallVideoGate.tsx: CallPage.tsx es dueño de
// CUÁNDO se llama a este componente y de qué pasa después (`onContinue`). Este componente solo
// muestra la ubicación — nunca decide si `call.start` debe mandarse.
//
// A diferencia de video, el contenido (calle/cruce/referencia/mapa) NO es la respuesta oculta —
// es lo que el trainee debe poder repetir de memoria durante la llamada. Solo los match_hints
// (nunca enviados a este componente, ver `ScenarioLocationAccess`) permanecen ocultos.
//
// `isLastStep` decide el label del botón (F14, Fase 2 Pass 7 decisión #2): "Continue" si un
// video gate sigue después en la secuencia, "Start Call" si esta es la última pantalla.
export default function PreCallLocationBriefing({
  scenarioTitle,
  location,
  briefing,
  isLastStep,
  onContinue,
}: {
  scenarioTitle: string
  location: ScenarioLocationAccess
  briefing: string
  isLastStep: boolean
  onContinue: () => void
}) {
  return (
    <div className="call-screen pre-call-location-briefing">
      <Header center={<div className="session-live"><MapPin size={22} /><strong>{scenarioTitle}</strong></div>} />
      <main className="call-main">
        <section className="call-card panel location-gate-card">
          <p className="video-gate-eyebrow">Before you call it in</p>
          <h1>Know the location</h1>
          <p className="video-gate-copy">This is where the incident is happening — be ready to give this to the dispatcher.</p>

          <LocationMiniMap
            mode="brief"
            value={{
              street: location.street,
              crossStreet: location.cross_street,
              landmark: location.landmark,
              markerX: location.marker_x,
              markerY: location.marker_y,
            }}
          />

          <div className="location-gate-text">
            {location.street && <p><strong>Street:</strong> {location.street}</p>}
            {location.cross_street && <p><strong>Cross street:</strong> {location.cross_street}</p>}
            {location.landmark && <p><strong>Landmark:</strong> {location.landmark}</p>}
          </div>

          {briefing && (
            <details className="location-gate-briefing">
              <summary>Full scenario briefing</summary>
              <p>{briefing}</p>
            </details>
          )}

          <button className="primary-cta" onClick={onContinue}>
            <Play fill="currentColor" size={22} />{isLastStep ? 'Start Call' : 'Continue'}
          </button>
        </section>
      </main>
    </div>
  )
}
