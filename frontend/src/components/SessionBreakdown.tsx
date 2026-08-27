import { AlertCircle, CheckCircle2, Languages, MapPin, MessageSquareText, Mic, Timer } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getScenarioLocationBrief, httpBaseFrom } from '../lib/api'
import { useEngineStore } from '../stores/engineStore'
import LocationMiniMap from './LocationMiniMap'
import ScoreRing from './ScoreRing'
import type { CoachingRating, CommunicationCoaching, ScenarioLocationAccess, TrainingSession } from '../types'

// Extraído de `ReviewPage` (roadmap Fase 2: "puntaje compuesto, desglose, y narrativa de
// debrief" + historial con posible "replay"). Es el mismo componente en las dos pantallas a
// propósito — separarlo en 3-4 pantallas distintas hubiera duplicado este layout completo; acá
// se reusa como la pantalla de decompresión post-llamada Y como el drill-down del historial.
// "Replay" se acota a la transcripción con timestamps (no hay audio grabado en ningún punto de
// esta arquitectura — ver NFR-07, cumplimiento regulatorio de grabación de voz, sin resolver).
export default function SessionBreakdown({ session }: { session: TrainingSession }) {
  const evaluation = session.evaluation
  const { bridgeUrl, authToken } = useEngineStore()
  const [locationBrief, setLocationBrief] = useState<ScenarioLocationAccess | null>(null)

  // Ubicación del incidente (docs/designs/ubicacion-del-incidente.md, Fase 2 Pass 1/F2, F17) —
  // el desglose por campo YA aparece gratis abajo en "Information Collected" (mismos arrays
  // `collected`/`missing` genéricos que cualquier CriticalDataPoint, cero cambios de render para
  // eso). El mini-mapa es la única pieza nueva de UI: aporta información real ahora que dibuja
  // geometría (F17), resaltando en verde/gris lo que el trainee mencionó — se omite en silencio
  // (nunca un mapa vacío) si el escenario no tiene ubicación configurada.
  useEffect(() => {
    if (!authToken || !session.scenario_id) return
    let cancelled = false
    getScenarioLocationBrief(httpBaseFrom(bridgeUrl), authToken, session.scenario_id).then((brief) => {
      if (!cancelled) setLocationBrief(brief)
    })
    return () => { cancelled = true }
  }, [session.scenario_id, authToken, bridgeUrl])

  if (!evaluation) {
    return (
      <div className="panel session-interrupted-card">
        <AlertCircle size={28} />
        <h2>Session interrupted</h2>
        <p>The connection dropped before this call ended — it wasn't scored so the trainee isn't penalized for a network issue.</p>
      </div>
    )
  }

  return (
    <div className="functional-review-grid">
      <section className="panel review-score-card">
        <div className="completed-title"><CheckCircle2 size={31} />Call Completed</div>
        <ScoreRing score={evaluation.overall_score} size={150} />
        <h2>{evaluation.overall_score} / 100</h2>
        <p>{evaluation.summary}</p>
      </section>
      {/* Motor de métricas (docs/designs/motor-de-metricas.md, Fase 2 Pass 1 de la revisión):
          `.category-scores` es la fórmula ponderada ya confirmada con el usuario (TODO-10
          RESOLVED) — NUNCA se le agregan barras nuevas acá. Las 4 dimensiones nuevas viven en
          "Communication Coaching" más abajo, como tarjetas cualitativas, no como más barras. */}
      <section className="panel category-scores">
        <h3>Category Scores</h3>
        {Object.entries(evaluation.category_scores).map(([label, score]) => (
          <div className="scorebar" key={label}>
            <div className="scorebar-label"><span>{formatCategoryLabel(label)}</span><strong>{score} / 100</strong></div>
            <div className="progress"><i style={{ width: `${score}%` }} /></div>
          </div>
        ))}
      </section>
      <section className="panel review-details">
        <h3>Information Collected</h3>
        {locationBrief && (
          <div className="location-review-overlay">
            <p className="location-review-heading"><MapPin size={14} />Location</p>
            <LocationMiniMap
              mode="review"
              value={{
                street: locationBrief.street,
                crossStreet: locationBrief.cross_street,
                landmark: locationBrief.landmark,
                markerX: locationBrief.marker_x,
                markerY: locationBrief.marker_y,
              }}
              collectedLabels={evaluation.collected}
            />
          </div>
        )}
        {evaluation.collected.map((item) => <p className="check-line ok" key={item}><CheckCircle2 size={17} />{item}</p>)}
        {evaluation.missing.map((item) => <p className="check-line bad" key={item}><AlertCircle size={17} />Missing: {item}</p>)}
      </section>
      <section className="panel review-details">
        <h3>Performance Notes</h3>
        {evaluation.strengths.map((item) => <p className="check-line ok" key={item}><CheckCircle2 size={17} />{item}</p>)}
        {evaluation.improvements.map((item) => <p className="check-line warn" key={item}><AlertCircle size={17} />{item}</p>)}
      </section>
      {evaluation.communication_coaching && (
        <CommunicationCoachingPanel coaching={evaluation.communication_coaching} judgeUnavailable={evaluation.judge_unavailable ?? false} />
      )}
      <section className="panel transcript-card full-transcript">
        <h3>Transcript & Timeline</h3>
        <div className="timeline">
          {session.transcript.map((entry, index) => (
            <div className="transcript-entry" key={`${entry.seconds}-${index}`}>
              <time>{formatTime(entry.seconds)}</time>
              <strong className={entry.role === 'dispatcher' ? 'dispatcher-text' : 'operator-text'}>{entry.role === 'dispatcher' ? 'Dispatcher' : 'Operator'}</strong>
              <span>{renderTranscriptText(entry.text)}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

// "Communication Coaching" — panel nuevo, separado a propósito de `.category-scores` (ver
// comentario arriba). Reusa `.rating.good/.improve/.critical` (globals.css) — clases que ya
// existían de un mockup anterior sin ningún .tsx que las usara hasta este cambio (Fase 2, Pass 5
// de la revisión). Degradación POR CAMPO: cada tarjeta se omite individualmente si su valor es
// `null`, nunca se oculta el panel completo por un solo campo faltante/fallido.
function CommunicationCoachingPanel({ coaching, judgeUnavailable }: { coaching: CommunicationCoaching; judgeUnavailable: boolean }) {
  const cards = [
    coaching.response_latency && {
      key: 'response_latency',
      icon: <Timer size={18} />,
      title: 'Response Latency',
      rating: coaching.response_latency.rating,
      tip: coaching.response_latency.tip,
    },
    coaching.transcription_confidence && {
      key: 'transcription_confidence',
      icon: <Mic size={18} />,
      title: 'Transcription Confidence',
      rating: coaching.transcription_confidence.rating,
      tip: coaching.transcription_confidence.tip,
    },
    coaching.coherence && {
      key: 'coherence',
      icon: <MessageSquareText size={18} />,
      title: 'Coherence',
      rating: coaching.coherence.rating,
      tip: coaching.coherence.tip,
    },
    coaching.english_quality && {
      key: 'english_quality',
      icon: <Languages size={18} />,
      title: 'English Quality',
      rating: coaching.english_quality.rating,
      tip: coaching.english_quality.tip,
    },
  ].filter(Boolean) as { key: string; icon: React.ReactNode; title: string; rating: CoachingRating; tip: string }[]

  if (!cards.length) {
    // Ningún campo tuvo datos (ej. llamada casi vacía) — nunca se muestra un panel vacío en
    // silencio, un mensaje explícito en su lugar (mismo principio que el resto del panel).
    return (
      <section className="panel review-details coaching-panel">
        <h3>Communication Coaching</h3>
        <p className="empty-copy">Not enough signal from this call to generate coaching notes.</p>
      </section>
    )
  }

  const missingJudgeCards = judgeUnavailable && !coaching.coherence && !coaching.english_quality

  return (
    <section className="panel review-details coaching-panel">
      <h3>Communication Coaching</h3>
      <div className="coaching-grid">
        {cards.map((card) => (
          <div className="coaching-tip" key={card.key}>
            <div className="coaching-tip-head">
              {card.icon}
              <span>{card.title}</span>
              <i className={`rating ${card.rating}`}>{formatRating(card.rating)}</i>
            </div>
            <p>{card.tip}</p>
          </div>
        ))}
      </div>
      {missingJudgeCards && (
        <p className="empty-copy coaching-judge-note">
          Coherence and English quality weren't available for this session — showing rule-based scores only.
        </p>
      )}
    </section>
  )
}

function formatRating(rating: CoachingRating): string {
  return rating === 'good' ? 'Good' : rating === 'improve' ? 'Improve' : 'Needs work'
}

// `[unclear: ...]` (ver `stt/whisper.py`, NFR-09) ya viaja inline en el texto — este render lo
// resalta visualmente en vez de mostrar los corchetes crudos (T10, docs/designs/motor-de-
// metricas.md), extendiendo el vocabulario que ya existe en vez de inventar un campo nuevo.
const UNCLEAR_PATTERN = /\[unclear: (.+?)\]/g

function renderTranscriptText(text: string): React.ReactNode {
  if (!text.includes('[unclear:')) return text

  const parts: React.ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null

  UNCLEAR_PATTERN.lastIndex = 0
  while ((match = UNCLEAR_PATTERN.exec(text))) {
    if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index))
    parts.push(
      <span className="unclear-span" key={match.index} title="Low STT confidence — the dispatcher was prompted to confirm this">
        <Mic size={11} />
        {match[1]}
      </span>,
    )
    lastIndex = match.index + match[0].length
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex))

  return parts
}

// `category_scores` keys ahora son las 4 categorías reales del motor de métricas
// (`snake_case`, ver `core/scoring.py`) — se muestran con un título legible.
function formatCategoryLabel(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatTime(seconds: number) {
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}
