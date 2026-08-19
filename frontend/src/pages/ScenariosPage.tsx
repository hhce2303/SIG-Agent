import { CheckCircle2, Headphones, Pencil, Play, Plus, ShieldAlert } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { useEngineStore } from '../stores/engineStore'

// Fase 2 (roadmap, TODO-11 resuelto): CRUD completo sobre el editor de escenarios estructurado
// — antes esta pantalla solo podía lanzar los escenarios ya hardcodeados.
export default function ScenariosPage() {
  const navigate = useNavigate()
  const { scenarios, selectedScenarioId, setConfig, startCall } = useEngineStore()
  const launch = (scenarioId: string, difficulty: string) => {
    setConfig({ selectedScenarioId: scenarioId, difficulty })
    window.setTimeout(() => {
      startCall()
      navigate('/call')
    }, 0)
  }
  return <AppShell active="Scenarios"><div className="content-page">
    <div className="page-heading-row">
      <div><h1>Scenario Library</h1><p>Select a structured scenario and begin a live training session.</p></div>
      <button className="blue-button" onClick={() => navigate('/scenarios/new')}><Plus size={17} />New Scenario</button>
    </div>
    <div className="scenario-grid">{scenarios.map((scenario) => <article className={`panel scenario-card ${selectedScenarioId === scenario.id ? 'selected' : ''}`} key={scenario.id}>
      <div className="scenario-card-icon">{scenario.difficulty === 'Hard' ? <ShieldAlert /> : <Headphones />}</div>
      <div><span className="eyebrow">{scenario.category} · {scenario.difficulty}</span><h2>{scenario.title}</h2><p>{scenario.description}</p></div>
      {selectedScenarioId === scenario.id && <span className="selected-badge"><CheckCircle2 size={15} />Selected</span>}
      <div className="scenario-card-actions">
        <button className="secondary-button" onClick={() => navigate(`/scenarios/${scenario.id}/edit`)}><Pencil size={16} />Edit</button>
        <button className="blue-button" onClick={() => launch(scenario.id, scenario.difficulty)}><Play size={17} />Start Scenario</button>
      </div>
    </article>)}</div>
  </div></AppShell>
}
