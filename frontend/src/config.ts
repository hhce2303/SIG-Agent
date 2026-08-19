const configuredBackendUrl = import.meta.env.VITE_BACKEND_WS_URL?.trim()

export const DEFAULT_BACKEND_WS_URL =
  configuredBackendUrl || 'ws://127.0.0.1:8765'
