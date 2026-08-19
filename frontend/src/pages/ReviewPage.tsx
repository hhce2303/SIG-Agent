import { AlertCircle, ArrowLeft, CheckCircle2, Download, RefreshCw } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import ScoreRing from '../components/ScoreRing'
import { useEngineStore } from '../stores/engineStore'

export default function ReviewPage() {
  const navigate = useNavigate()
  const { lastSession, scenarios, setConfig } = useEngineStore()
  if (!lastSession?.evaluation) return <AppShell active="Training"><div className="empty-state panel"><AlertCircle size={38} /><h1>No completed call</h1><p>Complete a training call to generate an evaluation.</p><button className="blue-button" onClick={() => navigate('/')}>Start training</button></div></AppShell>
  const evaluation = lastSession.evaluation
  const scenario = scenarios.find((item) => item.id === lastSession.scenario_id)
  const download = () => {
    const blob = new Blob([JSON.stringify(lastSession, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `sig-agent-${lastSession.id}.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }
  const retry = () => {
    setConfig({ selectedScenarioId: lastSession.scenario_id, difficulty: lastSession.difficulty })
    navigate('/')
  }
  return <AppShell active="Training"><div className="review-page"><div className="page-heading-row"><div><button className="text-link" onClick={() => navigate('/')}><ArrowLeft size={16} />Back to Training</button><h1>Call Review</h1><p>Scenario: {scenario?.title ?? lastSession.scenario_id} <span>•</span> Completed: {new Date(lastSession.ended_at ?? lastSession.started_at).toLocaleString()}</p></div><div className="page-actions"><button className="secondary-button" onClick={download}><Download size={17} />Download Report</button><button className="blue-button" onClick={retry}><RefreshCw size={17} />Train Again</button></div></div><div className="functional-review-grid"><section className="panel review-score-card"><div className="completed-title"><CheckCircle2 size={31} />Call Completed</div><ScoreRing score={evaluation.overall_score} size={150} /><h2>{evaluation.overall_score} / 100</h2><p>{evaluation.summary}</p></section><section className="panel category-scores"><h3>Category Scores</h3>{Object.entries(evaluation.category_scores).map(([label, score]) => <div className="scorebar" key={label}><div className="scorebar-label"><span>{label}</span><strong>{score} / 100</strong></div><div className="progress"><i style={{ width: `${score}%` }} /></div></div>)}</section><section className="panel review-details"><h3>Information Collected</h3>{evaluation.collected.map((item) => <p className="check-line ok" key={item}><CheckCircle2 size={17} />{item}</p>)}{evaluation.missing.map((item) => <p className="check-line bad" key={item}><AlertCircle size={17} />Missing: {item}</p>)}</section><section className="panel review-details"><h3>Performance Notes</h3>{evaluation.strengths.map((item) => <p className="check-line ok" key={item}><CheckCircle2 size={17} />{item}</p>)}{evaluation.improvements.map((item) => <p className="check-line warn" key={item}><AlertCircle size={17} />{item}</p>)}</section><section className="panel transcript-card full-transcript"><h3>Transcript & Timeline</h3><div className="timeline">{lastSession.transcript.map((entry, index) => <div className="transcript-entry" key={`${entry.seconds}-${index}`}><time>{formatTime(entry.seconds)}</time><strong className={entry.role === 'dispatcher' ? 'dispatcher-text' : 'operator-text'}>{entry.role === 'dispatcher' ? 'Dispatcher' : 'Operator'}</strong><span>{entry.text}</span></div>)}</div></section></div></div></AppShell>
}

function formatTime(seconds: number) {
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}
