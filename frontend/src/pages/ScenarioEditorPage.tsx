import { AlertCircle, Film, MapPin, ArrowLeft, Plus, Save, Trash2, Upload, X } from 'lucide-react'
import { FormEvent, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import AppShell from '../components/AppShell'
import LocationMiniMap from '../components/LocationMiniMap'
import {
  createScenario,
  deleteScenario,
  deleteScenarioLocation,
  deleteScenarioVideo,
  getScenario,
  getScenarioLocation,
  getScenarioVideoGroundTruth,
  httpBaseFrom,
  putScenarioLocation,
  putScenarioVideo,
  updateScenario,
  uploadVideo,
} from '../lib/api'
import { useEngineStore } from '../stores/engineStore'
import type { CriticalDataPointDef, ScenarioInput, ScenarioLocationInput, VideoGroundTruthPointDef } from '../types'

const EMPTY_LOCATION: ScenarioLocationInput = {
  street: '',
  cross_street: '',
  landmark: '',
  city_or_zone: '',
  additional_directions: '',
  match_hints: [],
  marker_x: null,
  marker_y: null,
}

const EMPTY_SCENARIO: ScenarioInput = {
  title: '',
  category: 'Police',
  difficulty: 'Medium',
  language: 'English',
  description: '',
  briefing: '',
  critical_data_points: [{ key: '', label: '', required: true, match_hints: [] }],
}

const EMPTY_GROUND_TRUTH_POINT: VideoGroundTruthPointDef = {
  key: '', label: '', match_hints: [], visible_from_seconds: 0, visible_to_seconds: 0, required: true,
}

// TODO-17: los hints se editan como texto separado por comas — más simple que un chip-input
// para un manager no-técnico, y es lo mismo que `core/scoring.py::_matches_point` necesita.
function parseHints(text: string): string[] {
  return text.split(',').map((hint) => hint.trim()).filter(Boolean)
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

  // Escenarios de video (docs/designs/escenarios-de-video.md) — solo tiene sentido una vez que
  // el escenario ya existe (PUT /scenarios/{id}/video necesita un scenario_id real), así que
  // esta sección entera queda oculta en modo "New Scenario" hasta guardar por primera vez.
  const [hasVideo, setHasVideo] = useState(false)
  const [videoPath, setVideoPath] = useState('')
  const [videoDuration, setVideoDuration] = useState(0)
  const [groundTruthPoints, setGroundTruthPoints] = useState<VideoGroundTruthPointDef[]>([EMPTY_GROUND_TRUTH_POINT])
  const [videoSaving, setVideoSaving] = useState(false)
  const [videoError, setVideoError] = useState<string>()
  const [uploading, setUploading] = useState(false)
  const [uploadedFileName, setUploadedFileName] = useState<string>()
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Ubicación del incidente (docs/designs/ubicacion-del-incidente.md) — mismo gate que video:
  // solo tiene sentido una vez que el escenario ya existe.
  const [hasLocation, setHasLocation] = useState(false)
  const [location, setLocation] = useState<ScenarioLocationInput>(EMPTY_LOCATION)
  const [locationSaving, setLocationSaving] = useState(false)
  const [locationError, setLocationError] = useState<string>()
  const [showMoreLocationDetails, setShowMoreLocationDetails] = useState(false)

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

  useEffect(() => {
    if (!isEditing || !authToken) return
    getScenarioVideoGroundTruth(httpBase, authToken, scenarioId!)
      .then((video) => {
        setHasVideo(true)
        setVideoPath(video.video_path)
        setVideoDuration(video.duration_seconds)
        setGroundTruthPoints(video.ground_truth_points.length ? video.ground_truth_points : [EMPTY_GROUND_TRUTH_POINT])
      })
      .catch(() => setHasVideo(false))  // 404 = sin video todavía, no es un error real que mostrar
  }, [isEditing, scenarioId, authToken, httpBase])

  useEffect(() => {
    if (!isEditing || !authToken) return
    getScenarioLocation(httpBase, authToken, scenarioId!)
      .then((loc) => {
        if (!loc) return  // sin ubicación todavía, no es un error real que mostrar
        setHasLocation(true)
        setLocation({
          street: loc.street,
          cross_street: loc.cross_street,
          landmark: loc.landmark,
          city_or_zone: loc.city_or_zone,
          additional_directions: loc.additional_directions,
          match_hints: loc.match_hints,
          marker_x: loc.marker_x,
          marker_y: loc.marker_y,
        })
      })
  }, [isEditing, scenarioId, authToken, httpBase])

  const updatePoint = (index: number, patch: Partial<CriticalDataPointDef>) => {
    setForm((state) => ({
      ...state,
      critical_data_points: state.critical_data_points.map((point, i) => (i === index ? { ...point, ...patch } : point)),
    }))
  }

  const addPoint = () => setForm((state) => ({
    ...state,
    critical_data_points: [...state.critical_data_points, { key: '', label: '', required: true, match_hints: [] }],
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

  const updateGroundTruthPoint = (index: number, patch: Partial<VideoGroundTruthPointDef>) => {
    setGroundTruthPoints((points) => points.map((point, i) => (i === index ? { ...point, ...patch } : point)))
  }
  const addGroundTruthPoint = () => setGroundTruthPoints((points) => [...points, EMPTY_GROUND_TRUTH_POINT])
  const removeGroundTruthPoint = (index: number) => setGroundTruthPoints((points) => points.filter((_, i) => i !== index))

  // ADR-0012 — sube el archivo real en vez de pedir una ruta ya colocada en el disco del
  // servidor. Solo llena los campos del formulario que ya existía (v1); "Attach video" abajo
  // sigue siendo el paso que efectivamente guarda el ground truth.
  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file || !authToken) return
    setUploading(true)
    setVideoError(undefined)
    try {
      const uploaded = await uploadVideo(httpBase, authToken, file)
      setVideoPath(uploaded.video_path)
      if (uploaded.duration_seconds != null) setVideoDuration(uploaded.duration_seconds)
      setUploadedFileName(file.name)
    } catch (err) {
      setVideoError(err instanceof Error ? err.message : 'Failed to upload video.')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const saveVideo = async (event: FormEvent) => {
    event.preventDefault()
    if (!authToken || !scenarioId) return
    setVideoSaving(true)
    setVideoError(undefined)
    try {
      await putScenarioVideo(httpBase, authToken, scenarioId, {
        video_path: videoPath.trim(),
        duration_seconds: videoDuration,
        content_type: 'video/mp4',
        ground_truth_points: groundTruthPoints
          .filter((point) => point.key.trim() && point.label.trim())
          .map((point) => ({ ...point, key: point.key.trim(), label: point.label.trim() })),
      })
      setHasVideo(true)
      refreshScenarios()  // el picker de Home/Scenarios necesita el `has_video` fresco
    } catch (err) {
      setVideoError(err instanceof Error ? err.message : 'Failed to attach video.')
    } finally {
      setVideoSaving(false)
    }
  }

  const removeVideo = async () => {
    if (!authToken || !scenarioId) return
    if (!window.confirm('Remove this video from the scenario? The trainee will get the text-only flow instead.')) return
    await deleteScenarioVideo(httpBase, authToken, scenarioId)
    setHasVideo(false)
    setVideoPath('')
    setVideoDuration(0)
    setGroundTruthPoints([EMPTY_GROUND_TRUTH_POINT])
    refreshScenarios()
  }

  // B8/Fase 3 Sección 1: la MISMA regla que `core/scoring.py::is_location_configured` — el
  // backend es la fuente autoritativa (rechaza con 422), esto es solo UX para no dejar que el
  // autor golpee ese 422 sin necesidad.
  const locationHasText = Boolean(
    location.street.trim() || location.cross_street.trim() || location.landmark.trim(),
  )
  const locationHasMarker = location.marker_x !== null && location.marker_y !== null
  const canSaveLocation = locationHasText || !locationHasMarker

  const saveLocation = async (event: FormEvent) => {
    event.preventDefault()
    if (!authToken || !scenarioId || !canSaveLocation) return
    setLocationSaving(true)
    setLocationError(undefined)
    try {
      await putScenarioLocation(httpBase, authToken, scenarioId, {
        ...location,
        street: location.street.trim(),
        cross_street: location.cross_street.trim(),
        landmark: location.landmark.trim(),
        city_or_zone: location.city_or_zone.trim(),
      })
      setHasLocation(true)
      refreshScenarios()  // el picker de Home/Scenarios necesita el `has_location` fresco
    } catch (err) {
      setLocationError(err instanceof Error ? err.message : 'Failed to save location.')
    } finally {
      setLocationSaving(false)
    }
  }

  const removeLocation = async () => {
    if (!authToken || !scenarioId) return
    if (!window.confirm('Remove this location from the scenario? The trainee will no longer see it before the call.')) return
    await deleteScenarioLocation(httpBase, authToken, scenarioId)
    setHasLocation(false)
    setLocation(EMPTY_LOCATION)
    refreshScenarios()
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
                <input
                  placeholder="match hints — real phrases, comma-separated (e.g. toyota camry, camry)"
                  className="scenario-point-hints"
                  value={point.match_hints.join(', ')}
                  onChange={(e) => updatePoint(index, { match_hints: parseHints(e.target.value) })}
                  title="TODO-17: the label alone rarely appears in natural speech — list the real words/phrases a trainee would actually say"
                />
                <label className="scenario-point-required"><input type="checkbox" checked={point.required} onChange={(e) => updatePoint(index, { required: e.target.checked })} />Required</label>
                <button type="button" className="secondary-button" onClick={() => removePoint(index)}><Trash2 size={15} /></button>
              </div>
            ))}
          </div>
          <p className="scenario-editor-hint">Match hints should be the real words a trainee would say (e.g. "toyota camry"), not the label itself — scoring compares against these, not the label text.</p>

          <div className="page-actions">
            <button className="blue-button" type="submit" disabled={saving}><Save size={17} />{saving ? 'Saving…' : 'Save scenario'}</button>
          </div>
        </form>

        {isEditing && (
          <form className="panel settings-form scenario-editor-form scenario-video-form" onSubmit={saveVideo}>
            <div className="scenario-points-header">
              <span className="scenario-video-heading"><Film size={17} />Video scenario (optional)</span>
              {hasVideo && <button type="button" className="secondary-button" onClick={removeVideo}><X size={15} />Remove video</button>}
            </div>
            <p className="scenario-editor-hint">
              Attach a video clip — the trainee watches it before the call instead of just reading the briefing above, then reports what they saw. Ground truth points below are what the trainee is scored against; the briefing above still drives the dispatcher's side of the conversation.
            </p>

            {videoError && <div className="call-notice error scenario-editor-error"><AlertCircle size={16} /><span>{videoError}</span></div>}

            <div className="video-upload-row">
              <input
                ref={fileInputRef}
                type="file"
                accept="video/mp4,video/quicktime,.mp4,.mov,.m4v"
                id="scenario-video-upload"
                className="video-upload-input"
                onChange={handleUpload}
                disabled={uploading}
              />
              <label htmlFor="scenario-video-upload" className="secondary-button video-upload-label">
                <Upload size={16} />{uploading ? 'Uploading…' : 'Choose video file to upload'}
              </label>
              {uploadedFileName && !uploading && <span className="video-upload-filename">✓ {uploadedFileName}</span>}
            </div>
            <p className="scenario-editor-hint">Uploads to this server (ADR-0012) — no need for anyone to place files on disk by hand. MP4/MOV, up to the server's configured size limit.</p>

            <div className="scenario-editor-grid">
              <label><span>Video file path {uploadedFileName ? '(filled in automatically after upload)' : '(or type a path already on the server)'}</span>
                <input placeholder="C:/videos/robbery_001.mp4" value={videoPath} onChange={(e) => setVideoPath(e.target.value)} required />
              </label>
              <label><span>Duration (seconds) {uploadedFileName && videoDuration ? '(auto-detected)' : ''}</span>
                <input type="number" min={1} step="0.1" value={videoDuration || ''} onChange={(e) => setVideoDuration(Number(e.target.value))} required />
              </label>
            </div>

            <div className="scenario-points-header">
              <span>Ground truth — what's actually visible in the video (scored, not sent to the dispatcher)</span>
              <button type="button" className="secondary-button" onClick={addGroundTruthPoint}><Plus size={16} />Add</button>
            </div>
            <div className="scenario-points-list">
              {groundTruthPoints.map((point, index) => (
                <div className="scenario-point-row video-ground-truth-row" key={index}>
                  <input placeholder="key (e.g. suspect_clothing)" value={point.key} onChange={(e) => updateGroundTruthPoint(index, { key: e.target.value })} />
                  <input placeholder="label (e.g. Suspect clothing)" value={point.label} onChange={(e) => updateGroundTruthPoint(index, { label: e.target.value })} />
                  <input
                    placeholder="match hints — real phrases (e.g. red jacket, hoodie)"
                    className="scenario-point-hints"
                    value={point.match_hints.join(', ')}
                    onChange={(e) => updateGroundTruthPoint(index, { match_hints: parseHints(e.target.value) })}
                  />
                  <label className="scenario-point-visible-at">
                    <span>Visible from</span>
                    <input type="number" min={0} step="0.5" value={point.visible_from_seconds} onChange={(e) => updateGroundTruthPoint(index, { visible_from_seconds: Number(e.target.value) })} />
                    <span>to</span>
                    <input type="number" min={0} step="0.5" value={point.visible_to_seconds} onChange={(e) => updateGroundTruthPoint(index, { visible_to_seconds: Number(e.target.value) })} />
                  </label>
                  <label className="scenario-point-required"><input type="checkbox" checked={point.required} onChange={(e) => updateGroundTruthPoint(index, { required: e.target.checked })} />Required</label>
                  <button type="button" className="secondary-button" onClick={() => removeGroundTruthPoint(index)}><Trash2 size={15} /></button>
                </div>
              ))}
            </div>
            <p className="scenario-editor-hint">Every ground truth point needs at least one match hint — the label alone won't score correctly (same TODO-17 fix as above).</p>

            <div className="page-actions">
              <button className="blue-button" type="submit" disabled={videoSaving}><Save size={17} />{videoSaving ? 'Saving…' : hasVideo ? 'Update video' : 'Attach video'}</button>
            </div>
          </form>
        )}

        {isEditing && (
          <form className="panel settings-form scenario-editor-form scenario-location-form" onSubmit={saveLocation}>
            <div className="scenario-points-header">
              <span className="scenario-video-heading"><MapPin size={17} />Incident location (optional)</span>
              {hasLocation && <button type="button" className="secondary-button" onClick={removeLocation}><X size={15} />Remove location</button>}
            </div>
            <p className="scenario-editor-hint">
              This is shown to the trainee before the call (and again, on request, during it) — it's what they need to be able to repeat back to the dispatcher, not a hidden answer key. Only the match hints below stay hidden; everything else is content the trainee sees.
            </p>

            {locationError && <div className="call-notice error scenario-editor-error"><AlertCircle size={16} /><span>{locationError}</span></div>}

            {/* F3 (design doc) — texto primero: no tiene sentido posicionar un flag con
                significado antes de que exista una calle que dibujar. */}
            <div className="scenario-editor-grid">
              <label><span>Street</span>
                <input placeholder="5th Avenue" value={location.street} onChange={(e) => setLocation({ ...location, street: e.target.value })} />
              </label>
              <label><span>Cross street</span>
                <input placeholder="Main Street" value={location.cross_street} onChange={(e) => setLocation({ ...location, cross_street: e.target.value })} />
              </label>
              <label><span>Landmark</span>
                <input placeholder="Westfield Shopping Center" value={location.landmark} onChange={(e) => setLocation({ ...location, landmark: e.target.value })} />
              </label>
              <label><span>Zone / city (optional, not scored)</span>
                <input placeholder="Downtown" value={location.city_or_zone} onChange={(e) => setLocation({ ...location, city_or_zone: e.target.value })} />
              </label>
            </div>

            <div className="location-minimap-editor">
              <LocationMiniMap
                mode="author"
                value={{
                  street: location.street,
                  crossStreet: location.cross_street,
                  landmark: location.landmark,
                  markerX: location.marker_x,
                  markerY: location.marker_y,
                }}
                onMarkerChange={(x, y) => setLocation({ ...location, marker_x: x, marker_y: y })}
              />
              {!locationHasText && (
                <p className="empty-copy">Enter a street name (or cross street/landmark) to place the marker on the map.</p>
              )}
            </div>

            <label>
              <span>Match hints — alternate phrasings a trainee might use, comma-separated (optional)</span>
              <input
                className="scenario-point-hints"
                placeholder="fifth ave, corner of 5th"
                value={location.match_hints.join(', ')}
                onChange={(e) => setLocation({ ...location, match_hints: parseHints(e.target.value) })}
                title="Same mechanism as critical data points (TODO-17) — these are compared against what the trainee says, not the field values themselves"
              />
            </label>

            <button
              type="button"
              className="text-link scenario-location-more-toggle"
              onClick={() => setShowMoreLocationDetails((value) => !value)}
            >
              {showMoreLocationDetails ? 'Hide' : 'Show'} additional directions
            </button>
            {showMoreLocationDetails && (
              <label>
                <span>Additional directions (narrative only — never scored)</span>
                <textarea
                  className="scenario-briefing"
                  rows={3}
                  placeholder="Behind the parking garage, near the loading dock…"
                  value={location.additional_directions}
                  onChange={(e) => setLocation({ ...location, additional_directions: e.target.value })}
                />
              </label>
            )}
            <p className="scenario-editor-hint">
              The marker's position doesn't affect scoring — it's a visual reference for you and the trainee. Only street/cross street/landmark text (matched against what the trainee says) counts toward completeness.
            </p>

            <div className="page-actions">
              <button className="blue-button" type="submit" disabled={locationSaving || !canSaveLocation}>
                <Save size={17} />{locationSaving ? 'Saving…' : hasLocation ? 'Update location' : 'Save location'}
              </button>
            </div>
          </form>
        )}
      </div>
    </AppShell>
  )
}
