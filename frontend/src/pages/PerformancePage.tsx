import { Activity, CircleGauge, RefreshCw, ShieldCheck } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import AppShell from '../components/AppShell'
import { useEngineStore } from '../stores/engineStore'

export default function PerformancePage() {
  const { history, scenarios, refreshHistory } = useEngineStore()
  const completed = history.filter((session) => session.evaluation)
  const average = completed.length ? Math.round(completed.reduce((sum, item) => sum + (item.evaluation?.overall_score ?? 0), 0) / completed.length) : 0
  const passing = completed.length ? Math.round(completed.filter((item) => (item.evaluation?.overall_score ?? 0) >= 75).length / completed.length * 100) : 0
  const trend = [...completed].reverse().map((item) => ({ date: new Date(item.started_at).toLocaleDateString(undefined, { month: 'numeric', day: 'numeric' }), score: item.evaluation?.overall_score ?? 0 }))
  return <AppShell active="Performance" role="Supervisor"><div className="performance-page"><div className="page-heading-row performance-heading"><div><h1>Performance Dashboard</h1><p>Analytics generated from completed local sessions.</p></div><button className="secondary-button" onClick={refreshHistory}><RefreshCw size={17} />Refresh</button></div><div className="kpi-grid three"><Kpi icon={<Activity />} label="Sessions" value={String(completed.length)} sub="Completed" /><Kpi icon={<CircleGauge />} label="Average Score" value={String(average)} sub="/ 100" /><Kpi icon={<ShieldCheck />} label="Pass Rate" value={`${passing}%`} sub="Passing (≥ 75)" /></div><div className="functional-analytics"><section className="panel trend-panel"><h3>Score Over Time</h3>{trend.length ? <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={trend}><CartesianGrid stroke="#16324b" vertical={false}/><XAxis dataKey="date" stroke="#7890a8"/><YAxis domain={[0,100]} stroke="#7890a8"/><Tooltip contentStyle={{ background:'#0b1b2c', border:'1px solid #1a3957', borderRadius:10 }}/><Area type="monotone" dataKey="score" stroke="#2d86ff" fill="rgba(45,134,255,.18)" strokeWidth={2}/></AreaChart></ResponsiveContainer></div> : <p className="empty-copy">Complete a session to begin tracking scores.</p>}</section><section className="panel session-table"><h3>Session History</h3><div className="table-head"><span>Scenario</span><span>Date</span><span>Difficulty</span><span>Score</span></div>{completed.map((session) => <div className="history-row" key={session.id}><strong>{scenarios.find((item) => item.id === session.scenario_id)?.title ?? session.scenario_id}</strong><span>{new Date(session.started_at).toLocaleString()}</span><span>{session.difficulty}</span><b className={(session.evaluation?.overall_score ?? 0) >= 75 ? 'success-text' : 'danger-text'}>{session.evaluation?.overall_score}</b></div>)}</section></div></div></AppShell>
}

function Kpi({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub: string }) {
  return <div className="panel kpi"><div className="kpi-icon">{icon}</div><div><span>{label}</span><strong>{value}</strong><small>{sub}</small></div></div>
}
