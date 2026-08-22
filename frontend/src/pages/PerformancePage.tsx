import { Activity, CircleGauge, RefreshCw, ShieldCheck } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import AppShell from '../components/AppShell'
import SessionBreakdown from '../components/SessionBreakdown'
import { useEngineStore } from '../stores/engineStore'
import type { CoachingRating, TrainingSession } from '../types'

// Motor de métricas (docs/designs/motor-de-metricas.md, T9 — Fase 2 Pass 7 decisión #3 de la
// revisión): UNA sola card de tendencia con selector de métrica, reusando el patrón "Score Over
// Time" existente, en vez de 4 cards casi idénticas (riesgo de "AI slop" por repetición).
const TREND_METRICS = [
  { key: 'overall', label: 'Overall Score' },
  { key: 'latency', label: 'Response Latency' },
  { key: 'quality', label: 'Communication Quality' },
] as const
type TrendMetric = (typeof TREND_METRICS)[number]['key']

// Traduce las tarjetas cualitativas (good/improve/critical) a un proxy numérico solo para
// graficar la tendencia — nunca se persiste ni se muestra como un "score" real en el drill-down
// (ahí siguen siendo `.rating` cualitativas, ver SessionBreakdown.tsx).
const RATING_SCORE: Record<CoachingRating, number> = { good: 100, improve: 60, critical: 20 }

function extractTrendValue(session: TrainingSession, metric: TrendMetric): number | null {
  const evaluation = session.evaluation
  if (!evaluation) return null
  if (metric === 'overall') return evaluation.overall_score

  const coaching = evaluation.communication_coaching
  if (!coaching) return null

  if (metric === 'latency') return coaching.response_latency?.average_ms ?? null

  const ratings = [coaching.coherence?.rating, coaching.english_quality?.rating, coaching.transcription_confidence?.rating]
    .filter((rating): rating is CoachingRating => Boolean(rating))
  return ratings.length ? Math.round(ratings.reduce((sum, rating) => sum + RATING_SCORE[rating], 0) / ratings.length) : null
}

// Fase 2 (roadmap): historial real — filtro por escenario, tendencia en el tiempo, y drill-down
// (reusa `SessionBreakdown`, la misma pantalla de fin de llamada) en vez de solo una lista.
// Visibilidad self-only ya la impone el servidor (`list_sessions` escopeado por supervisor_id
// del token) — esta pantalla solo muestra lo que el WS ya devolvió para esta sesión.
export default function PerformancePage() {
  const { history, scenarios, refreshHistory } = useEngineStore()
  const [scenarioFilter, setScenarioFilter] = useState('all')
  const [selectedId, setSelectedId] = useState<string>()
  const [trendMetric, setTrendMetric] = useState<TrendMetric>('overall')

  const filtered = useMemo(
    () => (scenarioFilter === 'all' ? history : history.filter((session) => session.scenario_id === scenarioFilter)),
    [history, scenarioFilter],
  )
  const scored = filtered.filter((session) => session.evaluation)
  const average = scored.length ? Math.round(scored.reduce((sum, item) => sum + (item.evaluation?.overall_score ?? 0), 0) / scored.length) : 0
  const passing = scored.length ? Math.round(scored.filter((item) => (item.evaluation?.overall_score ?? 0) >= 75).length / scored.length * 100) : 0
  // Cada sesión puntuada mantiene su lugar en el eje X aunque `value` sea `null` — un gap real
  // en la línea (recharts rompe el trazo en `null`), nunca interpolado a 0 (Pass 2 de la
  // revisión: mezcla de sesiones viejas/nuevas no debe leerse como "cayó a cero").
  const trend = [...scored].reverse().map((item) => ({
    date: new Date(item.started_at).toLocaleDateString(undefined, { month: 'numeric', day: 'numeric' }),
    value: extractTrendValue(item, trendMetric),
  }))
  const trendHasData = trend.some((point) => point.value !== null)
  const trendMetricLabel = TREND_METRICS.find((m) => m.key === trendMetric)?.label ?? ''
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
            <div className="panel-title">
              <h3>{trendMetricLabel} Over Time</h3>
              <select
                className="scenario-filter trend-metric-select"
                value={trendMetric}
                onChange={(e) => setTrendMetric(e.target.value as TrendMetric)}
              >
                {TREND_METRICS.map((metric) => <option key={metric.key} value={metric.key}>{metric.label}</option>)}
              </select>
            </div>
            {!trend.length ? (
              <p className="empty-copy">Complete a session to begin tracking scores.</p>
            ) : !trendHasData ? (
              <p className="empty-copy">Not enough data yet for this metric — it applies to sessions completed after this feature shipped.</p>
            ) : (
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={trend}>
                    <CartesianGrid stroke="#16324b" vertical={false} />
                    <XAxis dataKey="date" stroke="#7890a8" />
                    <YAxis domain={trendMetric === 'latency' ? ['auto', 'auto'] : [0, 100]} stroke="#7890a8" />
                    <Tooltip contentStyle={{ background: '#0b1b2c', border: '1px solid #1a3957', borderRadius: 10 }} />
                    <Area type="monotone" dataKey="value" stroke="#2d86ff" fill="rgba(45,134,255,.18)" strokeWidth={2} connectNulls={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
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
