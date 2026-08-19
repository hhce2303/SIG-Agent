import { Activity, CircleGauge, RefreshCw, ShieldCheck } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import AppShell from '../components/AppShell'
import SessionBreakdown from '../components/SessionBreakdown'
import { useEngineStore } from '../stores/engineStore'

// Fase 2 (roadmap): historial real — filtro por escenario, tendencia en el tiempo, y drill-down
// (reusa `SessionBreakdown`, la misma pantalla de fin de llamada) en vez de solo una lista.
// Visibilidad self-only ya la impone el servidor (`list_sessions` escopeado por supervisor_id
// del token) — esta pantalla solo muestra lo que el WS ya devolvió para esta sesión.
export default function PerformancePage() {
  const { history, scenarios, refreshHistory } = useEngineStore()
  const [scenarioFilter, setScenarioFilter] = useState('all')
  const [selectedId, setSelectedId] = useState<string>()

  const filtered = useMemo(
    () => (scenarioFilter === 'all' ? history : history.filter((session) => session.scenario_id === scenarioFilter)),
    [history, scenarioFilter],
  )
  const scored = filtered.filter((session) => session.evaluation)
  const average = scored.length ? Math.round(scored.reduce((sum, item) => sum + (item.evaluation?.overall_score ?? 0), 0) / scored.length) : 0
  const passing = scored.length ? Math.round(scored.filter((item) => (item.evaluation?.overall_score ?? 0) >= 75).length / scored.length * 100) : 0
  const trend = [...scored].reverse().map((item) => ({ date: new Date(item.started_at).toLocaleDateString(undefined, { month: 'numeric', day: 'numeric' }), score: item.evaluation?.overall_score ?? 0 }))
  const selected = history.find((session) => session.id === selectedId)

  return (
    <AppShell active="Performance" role="Supervisor">
      <div className="performance-page">
        <div className="page-heading-row performance-heading">
          <div><h1>Performance Dashboard</h1><p>Analytics generated from your own completed sessions.</p></div>
          <div className="page-actions">
            <select className="scenario-filter" value={scenarioFilter} onChange={(e) => setScenarioFilter(e.target.value)}>
              <option value="all">All scenarios</option>
              {scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.title}</option>)}
            </select>
            <button className="secondary-button" onClick={refreshHistory}><RefreshCw size={17} />Refresh</button>
          </div>
        </div>

        <div className="kpi-grid three">
          <Kpi icon={<Activity />} label="Sessions" value={String(filtered.length)} sub={`${scored.length} scored`} />
          <Kpi icon={<CircleGauge />} label="Average Score" value={String(average)} sub="/ 100" />
          <Kpi icon={<ShieldCheck />} label="Pass Rate" value={`${passing}%`} sub="Passing (≥ 75)" />
        </div>

        <div className="functional-analytics">
          <section className="panel trend-panel">
            <h3>Score Over Time</h3>
            {trend.length ? (
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={trend}>
                    <CartesianGrid stroke="#16324b" vertical={false} />
                    <XAxis dataKey="date" stroke="#7890a8" />
                    <YAxis domain={[0, 100]} stroke="#7890a8" />
                    <Tooltip contentStyle={{ background: '#0b1b2c', border: '1px solid #1a3957', borderRadius: 10 }} />
                    <Area type="monotone" dataKey="score" stroke="#2d86ff" fill="rgba(45,134,255,.18)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : <p className="empty-copy">Complete a session to begin tracking scores.</p>}
          </section>
          <section className="panel session-table">
            <h3>Session History</h3>
            <div className="table-head"><span>Scenario</span><span>Date</span><span>Difficulty</span><span>Score</span></div>
            {filtered.map((session) => (
              <button
                className={`history-row history-row-button ${selectedId === session.id ? 'selected' : ''}`}
                key={session.id}
                onClick={() => setSelectedId(selectedId === session.id ? undefined : session.id)}
              >
                <strong>{scenarios.find((item) => item.id === session.scenario_id)?.title ?? session.scenario_id}</strong>
                <span>{new Date(session.started_at).toLocaleString()}</span>
                <span>{session.difficulty}</span>
                {session.evaluation
                  ? <b className={session.evaluation.overall_score >= 75 ? 'success-text' : 'danger-text'}>{session.evaluation.overall_score}</b>
                  : <b className="danger-text">Not scored</b>}
              </button>
            ))}
            {!filtered.length && <p className="empty-copy">No sessions yet for this filter.</p>}
          </section>
        </div>

        {selected && (
          <div className="history-detail">
            <SessionBreakdown session={selected} />
          </div>
        )}
      </div>
    </AppShell>
  )
}

function Kpi({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub: string }) {
  return <div className="panel kpi"><div className="kpi-icon">{icon}</div><div><span>{label}</span><strong>{value}</strong><small>{sub}</small></div></div>
}
