import { AlertCircle, ArrowLeft, Plus, Save, Trash2 } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { createScenario, deleteScenario, getScenario, httpBaseFrom, updateScenario } from '../lib/api'
import { useEngineStore } from '../stores/engineStore'
import type { CriticalDataPointDef, ScenarioInput } from '../types'

const EMPTY_SCENARIO: ScenarioInput = {
  title: '',
  category: 'Police',
  difficulty: 'Medium',
  language: 'English',
  description: '',
  briefing: '',
  critical_data_points: [{ key: '', label: '', required: true }],
}

// Fase 2 (roadmap, TODO-11 resuelto): editor con campos estructurados guiados + una narrativa
// libre — no el editor de texto/plantillas descartado. `critical_data_points` es lo que el
// motor de métricas (`core/scoring.py`) usa para calcular completitud, así que es un campo de
// primera clase acá, no un detalle escondido.
export default function ScenarioEditorPage() {
  const navigate = useNavigate()
  const { scenarioId } = useParams()
  const isEditing = Boolean(scenarioId)
  const { bridgeUrl, authToken, refreshScenarios } = useEngineStore()
  const httpBase = httpBaseFrom(bridgeUrl)

  const [form, setForm] = useState<ScenarioInput>(EMPTY_SCENARIO)
  const [loading, setLoading] = useState(isEditing)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string>()

  useEffect(() => {
    if (!isEditing || !authToken) return
    getScenario(httpBase, authToken, scenarioId!)
      .then((scenario) => setForm({
        title: scenario.title,
        category: scenario.category,
        difficulty: scenario.difficulty,
        language: scenario.language,
        description: scenario.description,
        briefing: scenario.briefing,
        critical_data_points: scenario.critical_data_points.length ? scenario.critical_data_points : EMPTY_SCENARIO.critical_data_points,
      }))
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load scenario.'))
      .finally(() => setLoading(false))
  }, [isEditing, scenarioId, authToken, httpBase])

  const updatePoint = (index: number, patch: Partial<CriticalDataPointDef>) => {
    setForm((state) => ({
      ...state,
      critical_data_points: state.critical_data_points.map((point, i) => (i === index ? { ...point, ...patch } : point)),
    }))
  }

  const addPoint = () => setForm((state) => ({
    ...state,
    critical_data_points: [...state.critical_data_points, { key: '', label: '', required: true }],
  }))

  const removePoint = (index: number) => setForm((state) => ({
    ...state,
    critical_data_points: state.critical_data_points.filter((_, i) => i !== index),
  }))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!authToken) return
    setSaving(true)
    setError(undefined)
    try {
      const payload: ScenarioInput = {
        ...form,
        critical_data_points: form.critical_data_points
          .filter((point) => point.key.trim() && point.label.trim())
          .map((point) => ({ ...point, key: point.key.trim(), label: point.label.trim() })),
      }
      if (isEditing) await updateScenario(httpBase, authToken, scenarioId!, payload)
      else await createScenario(httpBase, authToken, payload)
      refreshScenarios()
      navigate('/scenarios')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save scenario.')
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    if (!authToken || !scenarioId) return
    if (!window.confirm(`Delete "${form.title}"? This cannot be undone.`)) return
    await deleteScenario(httpBase, authToken, scenarioId)
    refreshScenarios()
    navigate('/scenarios')
  }

  if (loading) return <AppShell active="Scenarios"><p className="empty-copy">Loading scenario…</p></AppShell>

  return (
    <AppShell active="Scenarios">
      <div className="content-page scenario-editor-page">
        <div className="page-heading-row">
          <div>
            <button className="text-link" onClick={() => navigate('/scenarios')}><ArrowLeft size={16} />Back to Scenarios</button>
            <h1>{isEditing ? 'Edit Scenario' : 'New Scenario'}</h1>
            <p>Structured fields drive the completeness score — the briefing is free-form context for the dispatcher.</p>
          </div>
          {isEditing && <button type="button" className="danger-button" onClick={remove}><Trash2 size={17} />Delete</button>}
        </div>

        {error && <div className="call-notice error scenario-editor-error"><AlertCircle size={16} /><span>{error}</span></div>}

        <form className="panel settings-form scenario-editor-form" onSubmit={submit}>
          <div className="scenario-editor-grid">
            <label><span>Title</span><input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required /></label>
            <label><span>Category</span><input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} required /></label>
            <label><span>Difficulty</span>
              <select value={form.difficulty} onChange={(e) => setForm({ ...form, difficulty: e.target.value })}>
                {['Easy', 'Medium', 'Hard', 'Expert'].map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
            <label><span>Language</span>
              <select value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })}>
                {['English', 'Spanish'].map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
          </div>

          <label><span>Short description (shown in the scenario library)</span>
            <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} required />
          </label>

          <label><span>Briefing (free-form narrative for the dispatcher)</span>
            <textarea className="scenario-briefing" value={form.briefing} onChange={(e) => setForm({ ...form, briefing: e.target.value })} rows={8} required />
          </label>

          <div className="scenario-points-header">
            <span>Critical data points (used to score completeness)</span>
            <button type="button" className="secondary-button" onClick={addPoint}><Plus size={16} />Add</button>
          </div>
          <div className="scenario-points-list">
            {form.critical_data_points.map((point, index) => (
              <div className="scenario-point-row" key={index}>
                <input placeholder="key (e.g. license_plate)" value={point.key} onChange={(e) => updatePoint(index, { key: e.target.value })} />
                <input placeholder="label shown to the trainee (e.g. License plate)" value={point.label} onChange={(e) => updatePoint(index, { label: e.target.value })} />
                <label className="scenario-point-required"><input type="checkbox" checked={point.required} onChange={(e) => updatePoint(index, { required: e.target.checked })} />Required</label>
                <button type="button" className="secondary-button" onClick={() => removePoint(index)}><Trash2 size={15} /></button>
              </div>
            ))}
          </div>

          <div className="page-actions">
            <button className="blue-button" type="submit" disabled={saving}><Save size={17} />{saving ? 'Saving…' : 'Save scenario'}</button>
          </div>
        </form>
      </div>
    </AppShell>
  )
}
