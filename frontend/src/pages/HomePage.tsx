import { Activity, CheckCircle2, Dice5, Globe2, Headphones, Play, ShieldCheck } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import ScoreRing from '../components/ScoreRing'
import { useEngineStore } from '../stores/engineStore'

export default function HomePage() {
  const navigate = useNavigate()
  const { connection, scenarios, history, selectedScenarioId, difficulty, language, trainingType, setConfig } = useEngineStore()
  const scored = history.filter((session) => session.evaluation)
  const average = scored.length ? Math.round(scored.reduce((sum, session) => sum + (session.evaluation?.overall_score ?? 0), 0) / scored.length) : 0
  // docs/designs/escenarios-de-video.md — no manda `call.start` directo: CallPage decide cuándo
  // (de inmediato si el escenario no tiene video, o después del gate de video si sí lo tiene).
  // Mismo motivo por el que ScenariosPage.tsx tampoco lo manda más — un solo lugar decide esto.
  const start = () => navigate('/call')
  return (
    <AppShell active="Home">
      <section className="home-layout">
        <div className="training-hero panel">
          <div className="hero-watermark" />
          <div className="dispatcher-outline"><Headphones size={35} /></div>
          <h1>Police Call Training</h1>
          <p>Practice real-world police call handling<br />and decision-making in a safe environment.</p>
          <div className={`ready-pill ${connection !== 'connected' ? 'offline' : ''}`}><CheckCircle2 size={20} />{connection === 'connected' ? 'Ready' : 'Connecting engine'}</div>
          <div className="hero-divider" />
          <button className="primary-cta" onClick={start}><Play fill="currentColor" size={27} />Start Training</button>
          <div className="selector-grid">
            <Selector
              label="Scenario"
              icon={<Dice5 size={18} />}
              value={selectedScenarioId}
              onChange={(value) => setConfig({ selectedScenarioId: value })}
              // docs/designs/escenarios-de-video.md — el marcador de texto es la única forma de
              // distinguir tipo dentro de un <option> nativo; el toggle de dos pestañas real
              // vive en ScenariosPage.tsx, esto es solo una pista rápida acá en Home.
              options={scenarios.map((scenario) => [scenario.id, scenario.has_video ? `🎬 ${scenario.title}` : scenario.title])}
            />
            <Selector label="Difficulty" icon={<Activity size={18} />} value={difficulty} onChange={(value) => setConfig({ difficulty: value })} options={['Easy', 'Medium', 'Hard', 'Expert'].map((value) => [value, value])} />
            <Selector label="Language" icon={<Globe2 size={18} />} value={language} onChange={(value) => setConfig({ language: value })} options={['English', 'Spanish'].map((value) => [value, value])} />
            <Selector label="Training Type" icon={<ShieldCheck size={18} />} value={trainingType} onChange={(value) => setConfig({ trainingType: value })} options={['Police', 'Police / EMS'].map((value) => [value, value])} />
          </div>
          <div className="previous-score"><span>◎</span> Previous Score: <strong>{scored[0]?.evaluation?.overall_score ?? '—'}</strong>{scored.length ? ' / 100' : ''}</div>
        </div>

        <aside className="home-rail">
          <div className="panel rail-card">
            <div className="panel-title"><h3>Recent Activity</h3><button>View all</button></div>
            <div className="activity-list">
              {history.slice(0, 5).map((session) => {
                const scenario = scenarios.find((item) => item.id === session.scenario_id)
                const score = session.evaluation?.overall_score ?? 0
                return <div className="activity-item" key={session.id}>
                  <div className="activity-icon blue"><Headphones size={19} /></div>
                  <div className="activity-copy"><strong>{scenario?.title ?? session.scenario_id}</strong><span>Score: {score} / 100</span></div>
                  <div className="activity-age"><span>{new Date(session.started_at).toLocaleDateString()}</span><i className={`status-dot ${score >= 75 ? 'success' : 'warning'}`} /></div>
                </div>
              })}
              {!history.length && <p className="empty-copy">Your completed sessions will appear here.</p>}
            </div>
          </div>
          <div className="panel rail-card performance-card">
            <h3>Performance Summary</h3>
            <div className="performance-overview">
              <ScoreRing score={average} size={112} />
              <dl>
                <div><dt>Average Score</dt><dd><strong>{average}</strong> / 100</dd></div>
                <div><dt>Sessions</dt><dd>{history.length}</dd></div>
                <div><dt>Engine</dt><dd className={connection === 'connected' ? 'success-text' : ''}>{connection}</dd></div>
              </dl>
            </div>
            <MiniLine />
          </div>
        </aside>
      </section>
    </AppShell>
  )
}

function Selector({ label, value, icon, options, onChange }: { label: string; value: string; icon: React.ReactNode; options: string[][]; onChange: (value: string) => void }) {
  return <label className="selector"><span>{label}</span><span className="select-control">{icon}<select value={value} onChange={(event) => onChange(event.target.value)}>{options.map(([optionValue, name]) => <option key={optionValue} value={optionValue}>{name}</option>)}</select></span></label>
}

function MiniLine() {
  return (
    <svg className="mini-line" viewBox="0 0 300 70" preserveAspectRatio="none" aria-hidden="true">
      <polyline points="0,45 32,18 64,35 95,21 126,32 158,44 190,33 222,29 255,49 300,20" fill="none" stroke="currentColor" strokeWidth="2" />
      {[0,32,64,95,126,158,190,222,255,300].map((x,i) => <circle key={x} cx={x} cy={[45,18,35,21,32,44,33,29,49,20][i]} r="2.5" fill="currentColor" />)}
    </svg>
  )
}
