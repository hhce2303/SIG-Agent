import { AlertCircle, ArrowUpRight, ClipboardCheck, Film, ShieldQuestion, Trash2, Upload } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { createIncident, deleteIncident, getImpactReport, httpBaseFrom, listIncidents, promoteIncidentToScenario, uploadVideo } from '../lib/api'
import { useEngineStore } from '../stores/engineStore'
import type { ImpactReport, IncidentInput, IncidentOutcome, VideoGroundTruthPointDef } from '../types'

const EMPTY_INCIDENT: IncidentInput = {
  occurred_at: Date.now(),
  supervisor_id: '',
  category: '',
  outcome_rating: 3,
  critical_data_captured: true,
  protocol_followed: true,
  notes: '',
}

// Fase 3 (roadmap, "cierre del lazo de impacto real"): captura manual de incidentes reales
// (decisión del usuario — no hay sistema de post-mortems existente con el que integrar) +
// correlación contra entrenamiento real ya completado ("¿trained sí/no?" nunca se pregunta acá,
// se deriva en el servidor de `PersistencePort.list_sessions`, ver `core/impact_metrics.py`) +
// el botón que cierra el lazo de retroalimentación (post-mortem → borrador de escenario).
//
// Sin control de acceso por rol (TODO-15, `core/ports.py::IncidentOutcome`): cualquier sesión
// autenticada ve esta pantalla, igual que ya pasa con el editor de escenarios.
export default function ImpactPage() {
  const navigate = useNavigate()
  const { bridgeUrl, authToken, role, refreshScenarios } = useEngineStore()
  const httpBase = httpBaseFrom(bridgeUrl)
  const isManager = role === 'manager'  // ADR-0011 — pista de UI; el servidor re-verifica esto

  const [incidents, setIncidents] = useState<IncidentOutcome[]>([])
  const [report, setReport] = useState<ImpactReport>()
  const [form, setForm] = useState<IncidentInput>(EMPTY_INCIDENT)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string>()

  // docs/designs/escenarios-de-video.md — adjuntar el video de un incidente real al promoverlo.
  // Solo managers lo ven (ADR-0011); un supervisor sigue con "Promote to scenario" sin video,
  // sin cambio de comportamiento.
  const [videoFormFor, setVideoFormFor] = useState<string>()
  const [videoPath, setVideoPath] = useState('')
  const [videoDuration, setVideoDuration] = useState(0)
  const [videoUploading, setVideoUploading] = useState(false)
  const [groundTruthPoints, setGroundTruthPoints] = useState<VideoGroundTruthPointDef[]>([
    { key: '', label: '', match_hints: [], visible_from_seconds: 0, visible_to_seconds: 0, required: true },
  ])

  const reload = () => {
    if (!authToken) return
    Promise.all([listIncidents(httpBase, authToken), getImpactReport(httpBase, authToken)])
      .then(([incidentList, impactReport]) => {
        setIncidents(incidentList)
        setReport(impactReport)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load incident data.'))
      .finally(() => setLoading(false))
  }

  useEffect(reload, [authToken, httpBase])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!authToken) return
    setError(undefined)
    try {
      await createIncident(httpBase, authToken, { ...form, occurred_at: new Date(form.occurred_at).getTime() })
      setForm(EMPTY_INCIDENT)
      reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to log incident.')
    }
  }

  const remove = async (id: string) => {
    if (!authToken) return
    if (!window.confirm('Delete this incident record? This cannot be undone.')) return
    await deleteIncident(httpBase, authToken, id)
    reload()
  }

  const promote = async (id: string, withVideo: boolean) => {
    if (!authToken) return
    try {
      const scenario = await promoteIncidentToScenario(
        httpBase,
        authToken,
        id,
        withVideo
          ? {
              video_path: videoPath.trim(),
              duration_seconds: videoDuration,
              content_type: 'video/mp4',
              ground_truth_points: groundTruthPoints
                .filter((point) => point.key.trim() && point.label.trim())
                .map((point) => ({ ...point, key: point.key.trim(), label: point.label.trim() })),
            }
          : undefined,
      )
      refreshScenarios()
      reload()
      setVideoFormFor(undefined)
      navigate(`/scenarios/${scenario.id}/edit`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to promote this incident to a scenario.')
    }
  }

  const updateGroundTruthPoint = (index: number, patch: Partial<VideoGroundTruthPointDef>) => {
    setGroundTruthPoints((points) => points.map((point, i) => (i === index ? { ...point, ...patch } : point)))
  }

  if (loading) return <AppShell active="Impact"><p className="empty-copy">Loading real-world impact data…</p></AppShell>

  return (
    <AppShell active="Impact">
      <div className="content-page">
        <div className="page-heading-row">
          <div>
            <h1>Real-World Impact</h1>
            <p>Log real incident outcomes and see how they correlate with completed training — trained/untrained is derived from actual session history, never entered by hand.</p>
          </div>
        </div>

        {error && <div className="call-notice error scenario-editor-error"><AlertCircle size={16} /><span>{error}</span></div>}

        {report && <ImpactComparison report={report} />}

        <div className="functional-analytics">
          <section className="panel">
            <h3>Log a real incident</h3>
            <form className="settings-form" onSubmit={submit}>
              <div className="scenario-editor-grid">
                <label><span>Date</span>
                  <input
                    type="date"
                    value={new Date(form.occurred_at).toISOString().slice(0, 10)}
                    onChange={(e) => setForm({ ...form, occurred_at: new Date(e.target.value).getTime() })}
                    required
                  />
                </label>
                <label><span>Supervisor ID</span>
                  <input value={form.supervisor_id} onChange={(e) => setForm({ ...form, supervisor_id: e.target.value })} required />
                </label>
                <label><span>Category</span>
                  <input placeholder="e.g. Vehicle Theft" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
                </label>
                <label><span>Outcome rating (1-5)</span>
                  <select value={form.outcome_rating} onChange={(e) => setForm({ ...form, outcome_rating: Number(e.target.value) })}>
                    {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </label>
              </div>
              <div className="scenario-editor-grid">
                <label className="scenario-point-required"><input type="checkbox" checked={form.critical_data_captured} onChange={(e) => setForm({ ...form, critical_data_captured: e.target.checked })} />Critical data captured</label>
                <label className="scenario-point-required"><input type="checkbox" checked={form.protocol_followed} onChange={(e) => setForm({ ...form, protocol_followed: e.target.checked })} />Protocol followed</label>
              </div>
              <label><span>Post-mortem notes (feeds the scenario library if promoted)</span>
                <textarea rows={4} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
              </label>
              <div className="page-actions">
                <button className="blue-button" type="submit"><ClipboardCheck size={17} />Log incident</button>
              </div>
            </form>
          </section>

          <section className="panel session-table">
            <h3>Logged incidents</h3>
            <div className="table-head"><span>Date</span><span>Supervisor</span><span>Category</span><span>Rating</span><span>Actions</span></div>
            {incidents.map((incident) => (
              <div key={incident.id}>
                <div className="history-row operator-row">
                  <span>{new Date(incident.occurred_at).toLocaleDateString()}</span>
                  <span>{incident.supervisor_id}</span>
                  <span>{incident.category || '—'}</span>
                  <b>{incident.outcome_rating}/5</b>
                  <span className="page-actions">
                    {incident.promoted_scenario_id ? (
                      <button className="secondary-button" onClick={() => navigate(`/scenarios/${incident.promoted_scenario_id}/edit`)}><ArrowUpRight size={15} />View scenario</button>
                    ) : (
                      <>
                        <button className="secondary-button" onClick={() => promote(incident.id, false)}><ArrowUpRight size={15} />Promote to scenario</button>
                        {isManager && (
                          <button
                            className="secondary-button"
                            onClick={() => {
                              // Estado limpio por incidente — evita que la ruta/duración de un
                              // video ya subido para OTRO incidente se filtre a este formulario.
                              setVideoPath('')
                              setVideoDuration(0)
                              setGroundTruthPoints([{ key: '', label: '', match_hints: [], visible_from_seconds: 0, visible_to_seconds: 0, required: true }])
                              setVideoFormFor(videoFormFor === incident.id ? undefined : incident.id)
                            }}
                          >
                            <Film size={15} />Promote with video
                          </button>
                        )}
                      </>
                    )}
                    <button className="secondary-button" onClick={() => remove(incident.id)}><Trash2 size={15} /></button>
                  </span>
                </div>

                {videoFormFor === incident.id && (
                  <div className="panel promote-video-form">
                    <p className="scenario-editor-hint">
                      Attaches this incident's real video to the new scenario (ADR-0011 — requires the manager role, which the server verifies independently of this UI).
                    </p>
                    <div className="video-upload-row">
                      <input
                        type="file"
                        accept="video/mp4,video/quicktime,.mp4,.mov,.m4v"
                        id={`incident-video-upload-${incident.id}`}
                        className="video-upload-input"
                        disabled={videoUploading}
                        onChange={async (e) => {
                          const file = e.target.files?.[0]
                          if (!file || !authToken) return
                          setVideoUploading(true)
                          setError(undefined)
                          try {
                            const uploaded = await uploadVideo(httpBase, authToken, file)
                            setVideoPath(uploaded.video_path)
                            if (uploaded.duration_seconds != null) setVideoDuration(uploaded.duration_seconds)
                          } catch (err) {
                            setError(err instanceof Error ? err.message : 'Failed to upload video.')
                          } finally {
                            setVideoUploading(false)
                            e.target.value = ''
                          }
                        }}
                      />
                      <label htmlFor={`incident-video-upload-${incident.id}`} className="secondary-button video-upload-label">
                        <Upload size={16} />{videoUploading ? 'Uploading…' : 'Choose video file to upload'}
                      </label>
                      {videoPath && !videoUploading && <span className="video-upload-filename">✓ uploaded</span>}
                    </div>
                    <div className="scenario-editor-grid">
                      <label><span>Video file path {videoPath ? '(filled in automatically after upload)' : '(or type a path already on the server)'}</span>
                        <input placeholder="C:/videos/robbery_001.mp4" value={videoPath} onChange={(e) => setVideoPath(e.target.value)} />
                      </label>
                      <label><span>Duration (seconds)</span>
                        <input type="number" min={1} step="0.1" value={videoDuration || ''} onChange={(e) => setVideoDuration(Number(e.target.value))} />
                      </label>
                    </div>
                    <div className="scenario-points-list">
                      {groundTruthPoints.map((point, index) => (
                        <div className="scenario-point-row" key={index}>
                          <input placeholder="key" value={point.key} onChange={(e) => updateGroundTruthPoint(index, { key: e.target.value })} />
                          <input placeholder="label (e.g. Suspect clothing)" value={point.label} onChange={(e) => updateGroundTruthPoint(index, { label: e.target.value })} />
                          <input
                            placeholder="match hints, comma-separated"
                            className="scenario-point-hints"
                            value={point.match_hints.join(', ')}
                            onChange={(e) => updateGroundTruthPoint(index, { match_hints: e.target.value.split(',').map((h) => h.trim()).filter(Boolean) })}
                          />
                        </div>
                      ))}
                    </div>
                    <div className="page-actions">
                      <button className="blue-button" disabled={!videoPath.trim() || !videoDuration} onClick={() => promote(incident.id, true)}>
                        <Film size={16} />Promote with this video
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
            {!incidents.length && <p className="empty-copy">No real incidents logged yet.</p>}
          </section>
        </div>
      </div>
    </AppShell>
  )
}

function ImpactComparison({ report }: { report: ImpactReport }) {
  const rows: Array<{ label: string; format: (stats: ImpactReport['trained']) => string }> = [
    { label: 'Incidents logged', format: (s) => String(s.sample_size) },
    { label: 'Avg. outcome rating', format: (s) => (s.avg_outcome_rating != null ? `${s.avg_outcome_rating.toFixed(1)} / 5` : '—') },
    { label: 'Critical data captured', format: (s) => (s.critical_data_capture_rate != null ? `${Math.round(s.critical_data_capture_rate * 100)}%` : '—') },
    { label: 'Protocol followed', format: (s) => (s.protocol_followed_rate != null ? `${Math.round(s.protocol_followed_rate * 100)}%` : '—') },
  ]

  return (
    <section className="panel">
      <div className="panel-title">
        <h3>Trained vs. untrained — real incidents</h3>
        {!report.is_conclusive && <span className="eyebrow"><ShieldQuestion size={13} style={{ verticalAlign: '-2px', marginRight: 4 }} />Not yet conclusive</span>}
      </div>
      {report.caveat && <p className="empty-copy">{report.caveat}</p>}
      <div className="table-head" style={{ gridTemplateColumns: '1.4fr 1fr 1fr' }}>
        <span>Metric</span><span>Trained before incident</span><span>Not trained</span>
      </div>
      {rows.map((row) => (
        <div className="history-row" style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr' }} key={row.label}>
          <span>{row.label}</span>
          <b>{row.format(report.trained)}</b>
          <b>{row.format(report.untrained)}</b>
        </div>
      ))}
    </section>
  )
}
