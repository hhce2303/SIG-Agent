import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { DEFAULT_BACKEND_WS_URL } from '../config'
import { voiceBridge, type ConnectionStatus } from '../lib/voiceBridge'
import type { CallStatus, EngineEvent, ScenarioSummary, TrainingSession, TranscriptEntry } from '../types'

const fallbackScenarios: ScenarioSummary[] = [
  { id: 'vehicle_theft', title: 'Vehicle Theft', category: 'Police', description: 'Report a recently stolen vehicle.', difficulty: 'Medium' },
  { id: 'domestic_dispute', title: 'Domestic Dispute', category: 'Police', description: 'Handle an active domestic disturbance.', difficulty: 'Hard' },
  { id: 'traffic_accident', title: 'Traffic Accident', category: 'Police / EMS', description: 'Report a collision with a possible injury.', difficulty: 'Medium' },
]

type PersistedConfig = 'selectedScenarioId' | 'difficulty' | 'language' | 'trainingType'

type EngineState = {
  initialized: boolean
  connection: ConnectionStatus
  engineVersion: string
  bridgeUrl: string
  userName: string
  scenarios: ScenarioSummary[]
  history: TrainingSession[]
  selectedScenarioId: string
  difficulty: string
  language: string
  trainingType: string
  activeScenario?: ScenarioSummary
  activeSessionId?: string
  callStatus: CallStatus
  transcript: TranscriptEntry[]
  operatorSpeaking: boolean
  dispatcherSpeaking: boolean
  engineActivity?: string
  recording: boolean
  lastSession?: TrainingSession
  error?: string
  warning?: string
  initialize: () => void
  setConfig: (patch: Partial<Pick<EngineState, PersistedConfig>>) => void
  updateSettings: (bridgeUrl: string, userName: string) => void
  startCall: () => void
  toggleRecording: () => void
  pause: () => void
  resume: () => void
  endCall: () => void
  refreshHistory: () => void
  clearNotice: () => void
}

export const useEngineStore = create<EngineState>()(persist((set, get) => ({
  initialized: false,
  connection: 'disconnected',
  engineVersion: '',
  bridgeUrl: DEFAULT_BACKEND_WS_URL,
  userName: 'Jordan Smith',
  scenarios: fallbackScenarios,
  history: [],
  selectedScenarioId: 'vehicle_theft',
  difficulty: 'Medium',
  language: 'English',
  trainingType: 'Police',
  callStatus: 'idle',
  transcript: [],
  operatorSpeaking: false,
  dispatcherSpeaking: false,
  engineActivity: undefined,
  recording: false,

  initialize: () => {
    if (get().initialized) return
    set({ initialized: true })
    voiceBridge.subscribeStatus((connection) => {
      set({ connection })
      if (connection === 'connected') {
        voiceBridge.send({ command: 'system.ping' })
        voiceBridge.send({ command: 'scenarios.list' })
        voiceBridge.send({ command: 'history.list' })
      }
    })
    voiceBridge.subscribe((event: EngineEvent) => {
      switch (event.event) {
        case 'system.ready': set({ engineVersion: event.version, error: undefined }); break
        case 'scenarios.data': set({ scenarios: event.scenarios.length ? event.scenarios : fallbackScenarios }); break
        case 'history.data': set({ history: event.sessions }); break
        case 'call.started': set({ activeSessionId: event.sessionId, activeScenario: event.scenario }); break
        case 'call.status': set({ callStatus: event.status }); break
        case 'operator.speaking': set({ operatorSpeaking: event.value, recording: event.value }); break
        case 'dispatcher.speaking': set({ dispatcherSpeaking: event.value }); break
        case 'engine.activity': set({ engineActivity: event.message ?? undefined }); break
        case 'transcript.operator':
          set((state) => ({ transcript: [...state.transcript, { role: 'operator', text: event.text, seconds: event.seconds }] })); break
        case 'transcript.dispatcher':
          set((state) => ({ transcript: [...state.transcript, { role: 'dispatcher', text: event.text, seconds: event.seconds }] })); break
        case 'session.completed':
          set((state) => ({ lastSession: event.session, history: [event.session, ...state.history.filter((item) => item.id !== event.session.id)], recording: false })); break
        case 'warning': set({ warning: event.message }); break
        case 'error': set({ error: event.message, recording: false, operatorSpeaking: false }); break
      }
    })
    voiceBridge.connect(get().bridgeUrl)
  },
  setConfig: (patch) => set(patch),
  updateSettings: (bridgeUrl, userName) => {
    set({ bridgeUrl, userName })
    voiceBridge.reconnect(bridgeUrl)
  },
  startCall: () => {
    const state = get()
    set({ transcript: [], lastSession: undefined, error: undefined, warning: undefined, callStatus: 'connecting' })
    voiceBridge.send({
      command: 'call.start',
      scenarioId: state.selectedScenarioId,
      difficulty: state.difficulty,
      language: state.language,
      trainingType: state.trainingType,
    })
  },
  toggleRecording: () => {
    if (get().recording) voiceBridge.send({ command: 'recording.stop' })
    else voiceBridge.send({ command: 'recording.start' })
  },
  pause: () => voiceBridge.send({ command: 'call.pause' }),
  resume: () => voiceBridge.send({ command: 'call.resume' }),
  endCall: () => voiceBridge.send({ command: 'call.end' }),
  refreshHistory: () => voiceBridge.send({ command: 'history.list' }),
  clearNotice: () => set({ error: undefined, warning: undefined }),
}), {
  name: 'sig-agent-settings',
  partialize: (state) => ({
    bridgeUrl: state.bridgeUrl,
    userName: state.userName,
    selectedScenarioId: state.selectedScenarioId,
    difficulty: state.difficulty,
    language: state.language,
    trainingType: state.trainingType,
  }),
}))
