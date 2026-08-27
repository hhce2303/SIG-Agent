// Cliente REST — Fase 2. Antes de esto el frontend no hacía ninguna llamada HTTP (todo era
// WebSocket, ver `voiceBridge.ts`); login (ADR-0008) y el CRUD de escenarios/ajustes viven en
// REST en el backend real, así que esto es nuevo, no una extensión de algo existente.

import type {
  ImpactReport,
  IncidentInput,
  IncidentOutcome,
  ScenarioDetail,
  ScenarioInput,
  ScenarioLocationAccess,
  ScenarioLocationDetail,
  ScenarioLocationInput,
  ScenarioVideoAccess,
  ScenarioVideoDetail,
  ScenarioVideoInput,
} from '../types'

export function httpBaseFrom(wsUrl: string): string {
  return wsUrl.replace(/^wss:\/\//, 'https://').replace(/^ws:\/\//, 'http://')
}

export function buildWsUrl(wsBase: string, sessionId: string, token: string): string {
  return `${wsBase}/ws/session/${sessionId}?token=${encodeURIComponent(token)}`
}

async function request<T>(url: string, options: RequestInit = {}, token?: string): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })

  if (!response.ok) {
    const body = await response.json().catch(() => undefined)
    throw new Error(body?.detail ?? `Request failed (${response.status})`)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export async function login(httpBase: string, supervisorId: string, passphrase: string) {
  const body = await request<{ session_id: string; token: string; role: string }>(`${httpBase}/auth/login`, {
    method: 'POST',
    body: JSON.stringify({ supervisor_id: supervisorId, passphrase }),
  })
  // ADR-0011 — `role` es solo una pista de UI (mostrar/ocultar controles de manager); la
  // aplicación real vive en el servidor, que re-deriva el rol del token, no de lo que mande
  // este cliente de vuelta.
  return { sessionId: body.session_id, token: body.token, role: body.role }
}

export function listScenarios(httpBase: string, token: string) {
  return request<ScenarioDetail[]>(`${httpBase}/scenarios`, {}, token)
}

export function getScenario(httpBase: string, token: string, id: string) {
  return request<ScenarioDetail>(`${httpBase}/scenarios/${id}`, {}, token)
}

export function createScenario(httpBase: string, token: string, scenario: ScenarioInput) {
  return request<ScenarioDetail>(
    `${httpBase}/scenarios`,
    { method: 'POST', body: JSON.stringify(scenario) },
    token,
  )
}

export function updateScenario(httpBase: string, token: string, id: string, scenario: ScenarioInput) {
  return request<ScenarioDetail>(
    `${httpBase}/scenarios/${id}`,
    { method: 'PUT', body: JSON.stringify(scenario) },
    token,
  )
}

export function deleteScenario(httpBase: string, token: string, id: string) {
  return request<void>(`${httpBase}/scenarios/${id}`, { method: 'DELETE' }, token)
}

// Escenarios de video — docs/designs/escenarios-de-video.md, ADR-0009/ADR-0010. `null` (no una
// excepción) cuando el escenario simplemente no tiene video adjunto (404) — ese es el estado
// por default de la mayoría de los escenarios hoy, y el caller (gate pre-llamada) debe seguir
// directo al flujo de hoy sin tratarlo como un error (hallazgo de diseño: el estado vacío es el
// más importante de no romper).
export async function getScenarioVideoAccess(
  httpBase: string,
  token: string,
  id: string,
): Promise<ScenarioVideoAccess | null> {
  try {
    return await request<ScenarioVideoAccess>(`${httpBase}/scenarios/${id}/video`, {}, token)
  } catch {
    return null
  }
}

export function getScenarioVideoGroundTruth(httpBase: string, token: string, id: string) {
  return request<ScenarioVideoDetail>(`${httpBase}/scenarios/${id}/video/ground-truth`, {}, token)
}

export function putScenarioVideo(httpBase: string, token: string, id: string, video: ScenarioVideoInput) {
  return request<ScenarioVideoDetail>(
    `${httpBase}/scenarios/${id}/video`,
    { method: 'PUT', body: JSON.stringify(video) },
    token,
  )
}

export function deleteScenarioVideo(httpBase: string, token: string, id: string) {
  return request<void>(`${httpBase}/scenarios/${id}/video`, { method: 'DELETE' }, token)
}

// Ubicación del incidente — docs/designs/ubicacion-del-incidente.md. `null` (no una excepción)
// cuando el escenario no tiene ubicación configurada (404) — mismo patrón que
// `getScenarioVideoAccess`: el gate de pre-llamada debe seguir directo al flujo de hoy, no
// tratarlo como un error.
export async function getScenarioLocationBrief(
  httpBase: string,
  token: string,
  id: string,
): Promise<ScenarioLocationAccess | null> {
  try {
    return await request<ScenarioLocationAccess>(`${httpBase}/scenarios/${id}/location/brief`, {}, token)
  } catch {
    return null
  }
}

export async function getScenarioLocation(
  httpBase: string,
  token: string,
  id: string,
): Promise<ScenarioLocationDetail | null> {
  try {
    return await request<ScenarioLocationDetail>(`${httpBase}/scenarios/${id}/location`, {}, token)
  } catch {
    return null
  }
}

export function putScenarioLocation(
  httpBase: string,
  token: string,
  id: string,
  location: ScenarioLocationInput,
) {
  return request<ScenarioLocationDetail>(
    `${httpBase}/scenarios/${id}/location`,
    { method: 'PUT', body: JSON.stringify(location) },
    token,
  )
}

export function deleteScenarioLocation(httpBase: string, token: string, id: string) {
  return request<void>(`${httpBase}/scenarios/${id}/location`, { method: 'DELETE' }, token)
}

// ADR-0012 — sube el archivo real en vez de pedir una ruta ya colocada en el disco del
// servidor (v1). No usa `request()`: un `FormData` necesita que el navegador ponga su propio
// `Content-Type: multipart/form-data; boundary=...`, poner el header a mano lo rompe.
//
// Deliberadamente NO tiene un `scenarioId` — el archivo no pertenece a ningún escenario todavía
// en el momento de subirlo (dos callers lo usan: `ScenarioEditorPage.tsx` para un escenario ya
// creado vía `PUT /scenarios/{id}/video`, e `ImpactPage.tsx` para uno que recién se crea en la
// misma llamada de `promote-to-scenario`).
export type ScenarioVideoUpload = {
  video_path: string
  video_checksum: string
  duration_seconds: number | null
  content_type: string
}

export async function uploadVideo(httpBase: string, token: string, file: File): Promise<ScenarioVideoUpload> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${httpBase}/videos/upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => undefined)
    throw new Error(body?.detail ?? `Upload failed (${response.status})`)
  }

  return (await response.json()) as ScenarioVideoUpload
}

export function getSettings(httpBase: string, token: string) {
  return request<{ tts_voice: string }>(`${httpBase}/settings`, {}, token)
}

export function updateTtsVoice(httpBase: string, token: string, ttsVoice: string) {
  return request<{ tts_voice: string }>(
    `${httpBase}/settings`,
    { method: 'PUT', body: JSON.stringify({ tts_voice: ttsVoice }) },
    token,
  )
}

// Fase 3 (roadmap): incidentes reales — captura manual + reporte de impacto agregado.
export function listIncidents(httpBase: string, token: string) {
  return request<IncidentOutcome[]>(`${httpBase}/incidents`, {}, token)
}

export function createIncident(httpBase: string, token: string, incident: IncidentInput) {
  return request<IncidentOutcome>(
    `${httpBase}/incidents`,
    { method: 'POST', body: JSON.stringify(incident) },
    token,
  )
}

export function deleteIncident(httpBase: string, token: string, id: string) {
  return request<void>(`${httpBase}/incidents/${id}`, { method: 'DELETE' }, token)
}

export function promoteIncidentToScenario(
  httpBase: string,
  token: string,
  id: string,
  video?: ScenarioVideoInput,
) {
  // ADR-0011: adjuntar `video` exige role=="manager" en el backend — el 403 se propaga tal
  // cual (mismo `request()` de siempre), este cliente no decide quién puede hacer qué.
  return request<ScenarioDetail>(
    `${httpBase}/incidents/${id}/promote-to-scenario`,
    { method: 'POST', body: JSON.stringify(video ? { video } : {}) },
    token,
  )
}

export function getImpactReport(httpBase: string, token: string) {
  return request<ImpactReport>(`${httpBase}/impact-report`, {}, token)
}
