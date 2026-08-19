export type ScenarioSummary = {
  id: string
  title: string
  category: string
  description: string
  difficulty: string
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

export type Evaluation = {
  overall_score: number
  category_scores: Record<string, number>
  collected: string[]
  missing: string[]
  strengths: string[]
  improvements: string[]
  summary: string
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
