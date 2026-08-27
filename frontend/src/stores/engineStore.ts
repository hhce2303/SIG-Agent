import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { DEFAULT_BACKEND_WS_URL } from '../config'
import { buildWsUrl, getScenarioLocationBrief, getScenarioVideoAccess, httpBaseFrom, login as apiLogin } from '../lib/api'
import { voiceBridge, type ConnectionStatus } from '../lib/voiceBridge'
import type {
  CallStatus,
  EngineEvent,
  ScenarioLocationAccess,
  ScenarioSummary,
  ScenarioVideoAccess,
  TrainingSession,
  TranscriptEntry,
} from '../types'

const fallbackScenarios: ScenarioSummary[] = [
  { id: 'vehicle_theft', title: 'Vehicle Theft', category: 'Police', description: 'Report a recently stolen vehicle.', difficulty: 'Medium', has_video: false, has_location: false },
  { id: 'domestic_dispute', title: 'Domestic Dispute', category: 'Police', description: 'Handle an active domestic disturbance.', difficulty: 'Hard', has_video: false, has_location: false },
  { id: 'traffic_accident', title: 'Traffic Accident', category: 'Police / EMS', description: 'Report a collision with a possible injury.', difficulty: 'Medium', has_video: false, has_location: false },
]

type PersistedConfig = 'selectedScenarioId' | 'difficulty' | 'language' | 'trainingType'

type EngineState = {
  initialized: boolean
  connection: ConnectionStatus
  engineVersion: string
  bridgeUrl: string
  userName: string
  // Fase 2 (login, ADR-0008): el WS real exige token — nada de esto se persiste en
  // localStorage (el token vive 8h, NFR-04, y no debe sobrevivir a un cierre de la app).
  sessionId?: string
  authToken?: string
  // ADR-0011 — pista de UI únicamente (ver lib/api.ts::login); nunca persistido (mismo motivo
  // que authToken no se persiste: no debe sobrevivir a un cierre de la app).
  role?: string
  authError?: string
  authenticating: boolean
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
  // Escenarios de video (docs/designs/escenarios-de-video.md) — `undefined` = todavía sin
  // chequear para el escenario seleccionado actual, `null` = chequeado, sin video (camino de
  // texto de siempre), objeto = sí hay video que mostrar antes de la llamada.
  videoAccess?: ScenarioVideoAccess | null
  videoAccessLoading: boolean
  // Ubicación del incidente (docs/designs/ubicacion-del-incidente.md) — mismo shape de tri-state
  // que videoAccess: `undefined` = sin chequear todavía, `null` = chequeado, sin ubicación
  // configurada, objeto = sí hay ubicación que mostrar antes de la llamada. A diferencia de
  // video, NO hay un `notifyLocationSeen` — la ubicación se puntúa incondicionalmente si está
  // configurada (nunca una exención por "el trainee la vio o no", ver Fase 3 Sección 1 del
  // design doc, hallazgo B1/B2).
  locationBrief?: ScenarioLocationAccess | null
  locationBriefLoading: boolean
  initialize: () => void
  login: (supervisorId: string, passphrase: string) => Promise<void>
  logout: () => void
  setConfig: (patch: Partial<Pick<EngineState, PersistedConfig>>) => void
  updateSettings: (bridgeUrl: string, userName: string) => void
  loadVideoAccess: (scenarioId: string) => Promise<ScenarioVideoAccess | null>
  notifyVideoEnded: (scenarioId: string) => void
  clearVideoAccess: () => void
  loadLocationBrief: (scenarioId: string) => Promise<ScenarioLocationAccess | null>
  clearLocationBrief: () => void
  startCall: () => void
  toggleRecording: () => void
  pause: () => void
  resume: () => void
  endCall: () => void
  refreshHistory: () => void
  refreshScenarios: () => void
  clearNotice: () => void
}

export const useEngineStore = create<EngineState>()(persist((set, get) => ({
  initialized: false,
  connection: 'disconnected',
  engineVersion: '',
  bridgeUrl: DEFAULT_BACKEND_WS_URL,
  userName: 'Jordan Smith',
  authenticating: false,
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
  videoAccess: undefined,
  videoAccessLoading: false,
  locationBrief: undefined,
  locationBriefLoading: false,

  initialize: () => {
    // Solo cablea los listeners del bridge — ya no conecta acá. La conexión real requiere un
    // token de sesión (ADR-0008/NFR-04), que recién existe después de `login()`.
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
        case 'scenarios.data': {
          const scenarios = event.scenarios.length ? event.scenarios : fallbackScenarios
          // `selectedScenarioId` se persiste en localStorage entre reinicios (ver `partialize`
          // abajo) — si el escenario que quedó seleccionado la última vez ya no existe (se
          // borró, o la base cambió), `call.start` mandaría un scenarioId que el backend no
          // reconoce ("Unknown scenario.") y la llamada se queda colgada en "Connecting…" sin
          // ningún gate ni error claro. Se corrige acá, en el único lugar donde la lista real de
          // escenarios llega, cayendo al primero disponible.
          const current = get().selectedScenarioId
          const stillValid = scenarios.some((scenario) => scenario.id === current)
          set({ scenarios, ...(stillValid ? {} : { selectedScenarioId: scenarios[0]?.id ?? '' }) })
          break
        }
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
  },

  login: async (supervisorId, passphrase) => {
    set({ authenticating: true, authError: undefined })
    try {
      const { sessionId, token, role } = await apiLogin(httpBaseFrom(get().bridgeUrl), supervisorId, passphrase)
      set({ sessionId, authToken: token, role, userName: supervisorId, authenticating: false })
      voiceBridge.connect(buildWsUrl(get().bridgeUrl, sessionId, token))
    } catch (error) {
      set({ authenticating: false, authError: error instanceof Error ? error.message : 'Login failed.' })
    }
  },

  logout: () => {
    voiceBridge.disconnect()
    set({ sessionId: undefined, authToken: undefined, role: undefined, connection: 'disconnected', callStatus: 'idle' })
  },

  setConfig: (patch) => set(patch),
  updateSettings: (bridgeUrl, userName) => {
    const changedBackend = bridgeUrl !== get().bridgeUrl
    set({ bridgeUrl, userName })
    // Un backend distinto significa una sesión de auth distinta (ADR-0008 no es multi-tenant
    // entre hosts) — forzamos un login nuevo en vez de reusar un token que ya no aplica.
    if (changedBackend) get().logout()
  },
  loadVideoAccess: async (scenarioId) => {
    const state = get()
    if (!state.authToken) return null
    set({ videoAccessLoading: true, videoAccess: undefined })
    const access = await getScenarioVideoAccess(httpBaseFrom(state.bridgeUrl), state.authToken, scenarioId)
    set({ videoAccess: access, videoAccessLoading: false })
    return access
  },
  notifyVideoEnded: (scenarioId) => voiceBridge.send({ command: 'video.ended', scenarioId }),
  // Se llama al efectivamente arrancar la llamada (ver CallPage.tsx) — sin esto, `videoAccess`
  // seguiría "verdadero" para siempre y CallPage renderizaría el gate de video otra vez encima
  // de una llamada ya en curso.
  clearVideoAccess: () => set({ videoAccess: undefined }),
  loadLocationBrief: async (scenarioId) => {
    const state = get()
    if (!state.authToken) return null
    set({ locationBriefLoading: true, locationBrief: undefined })
    const brief = await getScenarioLocationBrief(httpBaseFrom(state.bridgeUrl), state.authToken, scenarioId)
    set({ locationBrief: brief, locationBriefLoading: false })
    return brief
  },
  clearLocationBrief: () => set({ locationBrief: undefined }),
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
  refreshScenarios: () => voiceBridge.send({ command: 'scenarios.list' }),
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
