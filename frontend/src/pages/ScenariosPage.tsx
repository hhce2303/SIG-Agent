import { CheckCircle2, Film, Headphones, Pencil, Play, Plus, ShieldAlert, Type } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { useEngineStore } from '../stores/engineStore'

// Fase 2 (roadmap, TODO-11 resuelto): CRUD completo sobre el editor de escenarios estructurado
// — antes esta pantalla solo podía lanzar los escenarios ya hardcodeados.
//
// Escenarios de video (docs/designs/escenarios-de-video.md, /goal): el pedido original pide
// explícitamente DOS opciones — escenario de texto vs. de video — no una lista mezclada sin
// distinción. El toggle de abajo filtra sobre `has_video`; el video en sí se reproduce en
// CallPage.tsx (gate pre-llamada), esta pantalla solo elige CUÁL escenario.
export default function ScenariosPage() {
  const navigate = useNavigate()
  const { scenarios, selectedScenarioId, setConfig } = useEngineStore()
  const [mode, setMode] = useState<'text' | 'video'>('text')
  const visibleScenarios = scenarios.filter((scenario) => Boolean(scenario.has_video) === (mode === 'video'))

  // docs/designs/escenarios-de-video.md — ya no manda `call.start` acá (ver HomePage.tsx: un
  // solo lugar, CallPage, decide cuándo, según si el escenario tiene un video que mostrar antes).
  const launch = (scenarioId: string, difficulty: string) => {
    setConfig({ selectedScenarioId: scenarioId, difficulty })
    navigate('/call')
  }
  return <AppShell active="Scenarios"><div className="content-page">
    <div className="page-heading-row">
      <div><h1>Scenario Library</h1><p>Select a structured scenario and begin a live training session.</p></div>
      <button className="blue-button" onClick={() => navigate('/scenarios/new')}><Plus size={17} />New Scenario</button>
    </div>

    <div className="scenario-mode-toggle" role="tablist" aria-label="Scenario type">
      <button role="tab" aria-selected={mode === 'text'} className={mode === 'text' ? 'active' : ''} onClick={() => setMode('text')}>
        <Type size={16} />Text scenarios
      </button>
      <button role="tab" aria-selected={mode === 'video'} className={mode === 'video' ? 'active' : ''} onClick={() => setMode('video')}>
        <Film size={16} />Video scenarios
      </button>
    </div>

    <div className="scenario-grid">{visibleScenarios.map((scenario) => <article className={`panel scenario-card ${selectedScenarioId === scenario.id ? 'selected' : ''}`} key={scenario.id}>
      <div className="scenario-card-icon">{scenario.has_video ? <Film /> : scenario.difficulty === 'Hard' ? <ShieldAlert /> : <Headphones />}</div>
      <div><span className="eyebrow">{scenario.category} · {scenario.difficulty}</span><h2>{scenario.title}</h2><p>{scenario.description}</p></div>
      {selectedScenarioId === scenario.id && <span className="selected-badge"><CheckCircle2 size={15} />Selected</span>}
      <div className="scenario-card-actions">
        <button className="secondary-button" onClick={() => navigate(`/scenarios/${scenario.id}/edit`)}><Pencil size={16} />Edit</button>
        <button className="blue-button" onClick={() => launch(scenario.id, scenario.difficulty)}><Play size={17} />Start Scenario</button>
      </div>
    </article>)}
    {!visibleScenarios.length && (
      <p className="empty-copy">
        {mode === 'video' ? 'No video scenarios yet — attach a video to a scenario from its editor, or promote a real incident with video from the Impact page.' : 'No text scenarios yet.'}
      </p>
    )}
    </div>
  </div></AppShell>
}
