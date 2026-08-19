import { AlertCircle, CheckCircle2 } from 'lucide-react'
import ScoreRing from './ScoreRing'
import type { TrainingSession } from '../types'

// Extraído de `ReviewPage` (roadmap Fase 2: "puntaje compuesto, desglose, y narrativa de
// debrief" + historial con posible "replay"). Es el mismo componente en las dos pantallas a
// propósito — separarlo en 3-4 pantallas distintas hubiera duplicado este layout completo; acá
// se reusa como la pantalla de decompresión post-llamada Y como el drill-down del historial.
// "Replay" se acota a la transcripción con timestamps (no hay audio grabado en ningún punto de
// esta arquitectura — ver NFR-07, cumplimiento regulatorio de grabación de voz, sin resolver).
export default function SessionBreakdown({ session }: { session: TrainingSession }) {
  const evaluation = session.evaluation
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
        {evaluation.collected.map((item) => <p className="check-line ok" key={item}><CheckCircle2 size={17} />{item}</p>)}
        {evaluation.missing.map((item) => <p className="check-line bad" key={item}><AlertCircle size={17} />Missing: {item}</p>)}
      </section>
      <section className="panel review-details">
        <h3>Performance Notes</h3>
        {evaluation.strengths.map((item) => <p className="check-line ok" key={item}><CheckCircle2 size={17} />{item}</p>)}
        {evaluation.improvements.map((item) => <p className="check-line warn" key={item}><AlertCircle size={17} />{item}</p>)}
      </section>
      <section className="panel transcript-card full-transcript">
        <h3>Transcript & Timeline</h3>
        <div className="timeline">
          {session.transcript.map((entry, index) => (
            <div className="transcript-entry" key={`${entry.seconds}-${index}`}>
              <time>{formatTime(entry.seconds)}</time>
              <strong className={entry.role === 'dispatcher' ? 'dispatcher-text' : 'operator-text'}>{entry.role === 'dispatcher' ? 'Dispatcher' : 'Operator'}</strong>
              <span>{entry.text}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

// `category_scores` keys ahora son las 4 categorías reales del motor de métricas
// (`snake_case`, ver `core/scoring.py`) — se muestran con un título legible.
function formatCategoryLabel(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatTime(seconds: number) {
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}
