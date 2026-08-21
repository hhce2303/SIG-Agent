# ADR-0009: Mecanismo de auth para servir video de escenarios

- **Status:** accepted — resuelto en la misma sesión de implementación del plan de
  [escenarios-de-video.md](../../designs/escenarios-de-video.md) (TODO-19), sin bloquear en
  espera de aprobación externa, según instrucción explícita del usuario ("si hay algún gap abre
  el ADR pero lo intentaremos resolver aquí mismo").
- **Date:** 2026-08-21
- **Deciders:** implementación directa (Claude Code) sobre un hallazgo ya confirmado por la
  revisión de ingeniería de `/autoplan` (hallazgo 4.1) — no requirió una decisión de negocio del
  usuario, es una decisión técnica con una sola respuesta correcta dado el boundary de auth ya
  existente.

## Context and problem statement

Toda ruta REST de este servidor exige un bearer token HMAC (`_bearer_claims`, ver ADR-0008). Un
tag `<video>` HTML no puede adjuntar un header `Authorization` a su request — servir el archivo
de video como `StaticFiles` o devolver un path/URL crudo al frontend rompería ese boundary de
auth por completo, reabriendo exactamente el problema que ADR-0008/NFR-04 cerraron.
Adicionalmente, servir video requiere soporte de HTTP Range requests (para permitir rebobinar/
scrubbing antes de la llamada — ver hallazgo de diseño sobre permitir re-ver el video), lo que
descarta un fetch simple de todo el archivo.

## Decision drivers

- No se puede depender del header `Authorization` para la request que hace el propio `<video>`.
- Se necesita soporte de Range requests para scrubbing — no un blob completo en memoria.
- Ninguna dependencia nueva si se puede evitar (ADR-0008 ya estableció HMAC + stdlib como el
  patrón de este repo, sin librería externa de JWT).
- Reusar un patrón ya aceptado en este mismo repo (el WebSocket ya pasa su token de sesión como
  `?token=` en query param, ver `server/app.py:320`) en vez de inventar un mecanismo nuevo.

## Considered options

1. **Fetch-as-blob**: el frontend hace un `fetch()` autenticado (con bearer) del archivo completo,
   y lo expone al `<video>` vía `URL.createObjectURL`.
2. **Token de streaming firmado, de corta duración**: un endpoint REST autenticado con bearer
   (`GET /scenarios/{id}/video`) emite un token HMAC de vida corta (5 minutos) scopeado a ese
   `scenario_id`; el `<video src>` apunta a una ruta de streaming separada
   (`GET /scenarios/{id}/video/stream?token=...`) que valida ese token en vez del bearer, y
   soporta Range requests.
3. **Static file mount directo** (`StaticFiles`) sin ninguna capa de auth sobre el archivo.

## Decision

Se elige la opción 2. Mismo patrón que el WebSocket ya usa (token de vida acotada como query
param, verificado contra el recurso específico al que aplica — `scenario_id` en vez de
`session_id`), implementado con el mismo HMAC-SHA256 + base64 de stdlib que `HmacSessionTokenIssuer`
(ADR-0008), sin dependencia nueva (`auth/video_token.py::HmacVideoTokenIssuer`, TTL de 5 minutos —
deliberadamente corto porque el único uso es reproducir un video antes de una llamada de
práctica, no una sesión de trabajo completa). La ruta de streaming implementa Range requests
manualmente (sin depender de si la versión de Starlette instalada soporta Range en `FileResponse`,
que no se verificó) para permitir scrubbing.

La opción 1 (fetch-as-blob) se descarta como opción principal: carga el archivo completo en
memoria antes de poder reproducir nada y no da scrubbing eficiente sin reimplementar Range
requests de todos modos en el cliente — la opción 2 da lo mismo (auth) con mejor UX de
reproducción. La opción 3 se descarta: es exactamente el hallazgo de seguridad que este ADR existe
para evitar.

## Consequences

**Positive**
- El boundary de auth existente (ADR-0008) no se debilita — cualquier acceso al archivo de video
  pasa primero por un request bearer-autenticado que emite el token de streaming.
- Reusa un patrón ya aceptado en este repo (token de vida corta como query param) en vez de
  introducir un mecanismo de auth nuevo y distinto.
- Soporta scrubbing/rebobinar sin cargar el archivo completo en memoria del navegador.

**Negative**
- Dos rutas nuevas en vez de una (`/video` para obtener el token + `/video/stream` para
  consumirlo) — más superficie que un `StaticFiles` directo, a propósito.
- El token de streaming, aunque de vida corta, viaja en la URL (mismo trade-off ya aceptado para
  el token del WebSocket) — puede aparecer en logs de acceso del servidor si algo los captura sin
  redactar. Mismo riesgo ya aceptado por el WS, no uno nuevo introducido por esta decisión.

**Risks**
- Si en el futuro se sirven archivos de video mucho más grandes o con más tráfico concurrente
  (hoy: 1 usuario, NFR-11), el streaming manual por rangos puede necesitar revisarse por
  eficiencia — no es un riesgo real hoy dado el alcance confirmado del producto.

## Options not chosen

- **Fetch-as-blob (opción 1)**: viable como fallback si el streaming manual de Range diera
  problemas en producción, pero no se necesitó — revisitar solo si aparece evidencia real de
  que Range no funciona bien contra el cliente Electron.
- **Static file mount (opción 3)**: descartada, es la falla de seguridad que motivó este ADR.
