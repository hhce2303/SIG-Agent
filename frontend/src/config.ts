const configuredBackendUrl = import.meta.env.VITE_BACKEND_WS_URL?.trim()

// Fase 2: el default apuntaba a `ws://127.0.0.1:8765`, pero el servidor real
// (`server_main.py`, `SERVER_PORT`) escucha en el puerto 8000 y usa WSS/TLS por defecto
// (NFR-05) — el mismatch nunca se notó porque el backend real nunca hablaba el protocolo que
// el frontend ya esperaba (ver roadmap-3-fases.md, Fase 2). `bridgeUrl` es solo esquema+host+
// puerto, sin path — el path (`/ws/session/{id}`) y el token se agregan recién al conectar,
// después del login (ver `lib/api.ts::buildWsUrl`).
export const DEFAULT_BACKEND_WS_URL = configuredBackendUrl || 'wss://127.0.0.1:8000'
