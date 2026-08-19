// Cliente REST — Fase 2. Antes de esto el frontend no hacía ninguna llamada HTTP (todo era
// WebSocket, ver `voiceBridge.ts`); login (ADR-0008) y el CRUD de escenarios/ajustes viven en
// REST en el backend real, así que esto es nuevo, no una extensión de algo existente.

import type { ScenarioDetail, ScenarioInput } from '../types'

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
  const body = await request<{ session_id: string; token: string }>(`${httpBase}/auth/login`, {
    method: 'POST',
    body: JSON.stringify({ supervisor_id: supervisorId, passphrase }),
  })
  return { sessionId: body.session_id, token: body.token }
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
