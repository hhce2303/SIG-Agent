import { AlertCircle, ArrowLeft, Download, RefreshCw } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import SessionBreakdown from '../components/SessionBreakdown'
import { useEngineStore } from '../stores/engineStore'

export default function ReviewPage() {
  const navigate = useNavigate()
  const { lastSession, scenarios, setConfig } = useEngineStore()

  if (!lastSession) {
    return <AppShell active="Training"><div className="empty-state panel"><AlertCircle size={38} /><h1>No completed call</h1><p>Complete a training call to generate an evaluation.</p><button className="blue-button" onClick={() => navigate('/')}>Start training</button></div></AppShell>
  }

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

  return (
    <AppShell active="Training">
      <div className="review-page">
        <div className="page-heading-row">
          <div>
            <button className="text-link" onClick={() => navigate('/')}><ArrowLeft size={16} />Back to Training</button>
            <h1>Call Review</h1>
            <p>Scenario: {scenario?.title ?? lastSession.scenario_id} <span>•</span> Completed: {new Date(lastSession.ended_at ?? lastSession.started_at).toLocaleString()}</p>
          </div>
          <div className="page-actions">
            <button className="secondary-button" onClick={download}><Download size={17} />Download Report</button>
            <button className="blue-button" onClick={retry}><RefreshCw size={17} />Train Again</button>
          </div>
        </div>
        <SessionBreakdown session={lastSession} />
      </div>
    </AppShell>
  )
}
