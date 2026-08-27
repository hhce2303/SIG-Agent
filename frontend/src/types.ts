export type ScenarioSummary = {
  id: string
  title: string
  category: string
  description: string
  difficulty: string
  // docs/designs/escenarios-de-video.md — deriva de si el escenario tiene un ScenarioVideo
  // adjunto en el backend; `Scenario` en sí no cambió (ver ADR-0009/ADR-0010).
  has_video: boolean
  // docs/designs/ubicacion-del-incidente.md — idem, deriva de si hay un ScenarioLocation con al
  // menos un campo de texto configurado (`core/scoring.py::is_location_configured`).
  has_location: boolean
}

// Fase 2 (roadmap, TODO-11 resuelto: campos estructurados + narrativa libre). `ScenarioSummary`
// arriba sigue siendo exactamente lo que ya manda `scenarios.data` por WS (sin romper el
// contrato) — esto es lo que agrega el editor CRUD nuevo, servido por REST.
export type CriticalDataPointDef = {
  key: string
  label: string
  required: boolean
  // TODO-17 — frases de contenido real esperadas (no el label de UI), ver core/scoring.py.
  match_hints: string[]
}

export type ScenarioDetail = ScenarioSummary & {
  language: string
  briefing: string
  critical_data_points: CriticalDataPointDef[]
  created_at: number
  updated_at: number
}

export type ScenarioInput = {
  title: string
  category: string
  difficulty: string
  language: string
  description: string
  briefing: string
  critical_data_points: CriticalDataPointDef[]
}

// Escenarios de video — docs/designs/escenarios-de-video.md, ADR-0009/ADR-0010.
export type VideoGroundTruthPointDef = {
  key: string
  label: string
  match_hints: string[]
  visible_from_seconds: number
  visible_to_seconds: number
  required: boolean
}

// Lo que ve el entrenando antes de la llamada — SIN match_hints/timestamps (ver ADR-0010,
// nunca se manda la respuesta correcta antes de que hable).
export type ScenarioVideoAccess = {
  content_type: string
  duration_seconds: number
  stream_url: string
}

// Vista de autoría (editor) — SÍ incluye match_hints/timestamps.
export type ScenarioVideoDetail = {
  scenario_id: string
  video_path: string
  video_checksum: string
  duration_seconds: number
  content_type: string
  ground_truth_points: VideoGroundTruthPointDef[]
  created_at: number
  updated_at: number
}

export type ScenarioVideoInput = {
  video_path: string
  duration_seconds: number
  content_type: string
  ground_truth_points: VideoGroundTruthPointDef[]
}

// Ubicación del incidente — docs/designs/ubicacion-del-incidente.md. A diferencia de video, el
// contenido descriptivo (calle/cruce/referencia) NO es la respuesta oculta — el trainee lo ve
// antes de la llamada (PreCallLocationBriefing) y opcionalmente durante (InCallLocationPanel).
// Solo `match_hints` (las frases de scoring) se quedan en la vista de autoría.
export type ScenarioLocationAccess = {
  street: string
  cross_street: string
  landmark: string
  city_or_zone: string
  additional_directions: string
  marker_x: number | null
  marker_y: number | null
}

export type ScenarioLocationDetail = ScenarioLocationAccess & {
  scenario_id: string
  match_hints: string[]
  created_at: number
  updated_at: number
}

export type ScenarioLocationInput = {
  street: string
  cross_street: string
  landmark: string
  city_or_zone: string
  additional_directions: string
  match_hints: string[]
  marker_x: number | null
  marker_y: number | null
}

export type TranscriptEntry = { role: 'operator' | 'dispatcher'; text: string; seconds: number }

export type CallStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'paused'
  | 'processing'
  | 'completed'
  | 'error'

// Motor de métricas — docs/designs/motor-de-metricas.md. `rating` es la misma taxonomía en las
// 4 tarjetas del panel de "Communication Coaching" (Fase 2, Pass 1 de la revisión): mapea 1:1 a
// las clases CSS `.rating.good/.improve/.critical` (ya existían en globals.css, sin usar en
// ningún .tsx hasta este cambio).
export type CoachingRating = 'good' | 'improve' | 'critical'

export type ResponseLatencyCoaching = {
  rating: CoachingRating
  average_ms: number
  sample_count: number
  fastest_ms: number
  slowest_ms: number
  tip: string
}

export type TranscriptionConfidenceCoaching = {
  rating: CoachingRating
  segment_count: number
  low_confidence_segment_count: number
  tip: string
}

export type SimpleCoaching = {
  rating: CoachingRating
  tip: string
}

// Deliberadamente NO se llama "accent"/"pronunciation" en ningún campo — ver Fase 1 0A punto 1
// de la revisión: Whisper no tiene clasificador de acento, `transcription_confidence` es la
// señal real (confianza de transcripción), nombrada por lo que mide.
export type CommunicationCoaching = {
  response_latency: ResponseLatencyCoaching | null
  transcription_confidence: TranscriptionConfidenceCoaching | null
  coherence: SimpleCoaching | null
  english_quality: SimpleCoaching | null
}

export type Evaluation = {
  overall_score: number
  category_scores: Record<string, number>
  collected: string[]
  missing: string[]
  strengths: string[]
  improvements: string[]
  summary: string
  // Escenarios de video (ADR-0010) — `undefined` en sesiones históricas persistidas ANTES de
  // este campo, `null` cuando la sesión actual no tuvo video o nunca mandó `video.ended` antes
  // de `call.start`. Ninguno de los dos casos es "0 segundos" — tratar como "no aplica", nunca
  // mostrar un cronómetro en 0 (ver hallazgo de diseño sobre no puntuar esto como reflejos).
  video_reaction_seconds?: number | null
  // Motor de métricas (T1-T4/T13) — mismo patrón de opcionalidad: `undefined` en sesiones
  // históricas anteriores a este cambio (el panel de coaching completo no se muestra, nunca con
  // campos en 0/vacío). Presente en sesiones nuevas, con cada sub-campo en `null` si no hubo
  // muestra o el juez LLM no corrió — degradación POR CAMPO, nunca por panel completo.
  communication_coaching?: CommunicationCoaching
  // `true` si el juez LLM (coherencia/inglés) no corrió o falló esta sesión — informativo, para
  // distinguir "no configurado/falló" de "no aplica" en la copy del panel.
  judge_unavailable?: boolean
}

export type TrainingSession = {
  id: string
  scenario_id: string
  difficulty: string
  language: string
  training_type: string
  started_at: string
  ended_at: string | null
  status: CallStatus
  transcript: TranscriptEntry[]
  evaluation: Evaluation | null
}

export type EngineEvent =
  | { event: 'system.ready'; version: string }
  | { event: 'scenarios.data'; scenarios: ScenarioSummary[] }
  | { event: 'history.data'; sessions: TrainingSession[] }
  | { event: 'call.started'; sessionId: string; scenario: ScenarioSummary }
  | { event: 'call.status'; status: CallStatus }
  | { event: 'operator.speaking'; value: boolean }
  | { event: 'dispatcher.speaking'; value: boolean }
  | { event: 'engine.activity'; message: string | null }
  | { event: 'transcript.operator' | 'transcript.dispatcher'; text: string; seconds: number }
  | { event: 'session.completed'; session: TrainingSession }
  | { event: 'warning'; message: string }
  | { event: 'error'; message: string; recoverable: boolean }

// Fase 3 (roadmap, "cierre del lazo de impacto real"): captura manual de incidentes reales
// (decisión del usuario — no existe ningún sistema de post-mortems con el que integrar) y el
// reporte agregado que los correlaciona contra entrenamiento real ya completado.
export type IncidentInput = {
  occurred_at: number
  supervisor_id: string
  category: string
  outcome_rating: number
  critical_data_captured: boolean
  protocol_followed: boolean
  notes: string
}

export type IncidentOutcome = IncidentInput & {
  id: string
  reported_by: string
  promoted_scenario_id: string
  created_at: number
}

export type ImpactGroupStats = {
  sample_size: number
  avg_outcome_rating: number | null
  critical_data_capture_rate: number | null
  protocol_followed_rate: number | null
}

export type ImpactReport = {
  trained: ImpactGroupStats
  untrained: ImpactGroupStats
  total_incidents: number
  is_conclusive: boolean
  caveat: string
}

export type EngineCommand =
  | { command: 'system.ping' }
  | { command: 'scenarios.list' }
  | { command: 'history.list' }
  | {
      command: 'call.start'
      scenarioId: string
      difficulty: string
      language: string
      trainingType: string
    }
  | { command: 'call.pause' }
  | { command: 'call.resume' }
  | { command: 'call.end' }
  | { command: 'recording.start' }
  | { command: 'recording.stop' }
  // Escenarios de video — mandado cuando el video pre-llamada terminó (o se saltó), SIEMPRE
  // antes de `call.start`, nunca durante la llamada (ver server/app.py, hallazgo de diseño
  // sobre no auto-avanzar de "terminó el video" a "empezó la llamada").
  | { command: 'video.ended'; scenarioId: string }
