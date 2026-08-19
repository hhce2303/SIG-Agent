# Requisitos del backend para SIG Agent Frontend

Este documento es el contrato de integración entre los equipos de frontend y
backend. Describe el protocolo que consume la interfaz actual.

## 1. Transporte

- WebSocket con mensajes JSON codificados en UTF-8.
- Desarrollo local predeterminado: `wss://127.0.0.1:8000` (Fase 2: corregido — el servidor real
  usa WSS/TLS por defecto, NFR-05, y escucha en el puerto 8000, no 8765).
- Producción remota: `wss://` obligatorio.
- El WebSocket real vive en `/ws/session/{session_id}?token=...` — el `session_id` y el `token`
  salen de `POST /auth/login` (ver §10). Sin login previo, el servidor rechaza la conexión
  (NFR-04) — el cliente debe autenticarse antes de intentar conectar el WebSocket.
- Un objeto JSON completo por frame de texto.
- Tamaño máximo recomendado por mensaje: 1 MiB.
- El backend debe aceptar reconexiones y tratar cada conexión como una sesión
  de cliente independiente.
- Al conectarse debe enviar inmediatamente `system.ready`, `scenarios.data` e
  `history.data`. El frontend también puede solicitarlos otra vez.

No deben enviarse claves, tokens de proveedores de IA ni detalles internos de
excepciones al cliente.

## 2. Responsabilidad de audio

La implementación actual usa este modelo:

```text
Frontend                     Backend en el equipo del usuario
recording.start ───────────▶ abre el micrófono
recording.stop  ───────────▶ cierra/graba/transcribe
                            genera respuesta y reproduce TTS
eventos JSON     ◀────────── estado + transcripción
```

Por tanto, el backend debe ejecutarse en el mismo equipo que tiene el
micrófono y los altavoces. Si el equipo decide alojarlo remotamente, este
contrato debe evolucionar primero para transmitir audio desde el frontend; no
basta con cambiar `ws://` por una URL remota.

## 3. Formato general

Comando enviado por el frontend:

```json
{ "command": "system.ping" }
```

Evento enviado por el backend:

```json
{ "event": "system.ready", "version": "0.2.0" }
```

Los nombres de propiedades son sensibles a mayúsculas y minúsculas. No se
deben renombrar campos existentes sin incrementar la versión del protocolo.
Se permite agregar campos opcionales porque el frontend ignora los que no
conoce.

## 4. Comandos requeridos

| Comando | Propiedades adicionales | Resultado esperado |
|---|---|---|
| `system.ping` | Ninguna | `system.ready` |
| `scenarios.list` | Ninguna | `scenarios.data` |
| `history.list` | Ninguna | `history.data` |
| `call.start` | `scenarioId`, `difficulty`, `language`, `trainingType` | Inicia una sesión |
| `call.pause` | Ninguna | Estado `paused` |
| `call.resume` | Ninguna | Estado `connected` |
| `call.end` | Ninguna | Evalúa, guarda y completa la sesión |
| `recording.start` | Ninguna | Abre el micrófono |
| `recording.stop` | Ninguna | Transcribe y genera la respuesta |

Ejemplo de inicio:

```json
{
  "command": "call.start",
  "scenarioId": "vehicle_theft",
  "difficulty": "Medium",
  "language": "English",
  "trainingType": "Police"
}
```

## 5. Eventos requeridos

### Sistema y catálogos

```json
{ "event": "system.ready", "version": "0.2.0" }
```

```json
{
  "event": "scenarios.data",
  "scenarios": [
    {
      "id": "vehicle_theft",
      "title": "Vehicle Theft",
      "category": "Police",
      "description": "Report a recently stolen vehicle.",
      "difficulty": "Medium"
    }
  ]
}
```

```json
{ "event": "history.data", "sessions": [] }
```

### Ciclo de llamada

Estados permitidos: `idle`, `connecting`, `connected`, `paused`, `processing`,
`completed` y `error`.

```json
{ "event": "call.status", "status": "connected" }
```

```json
{
  "event": "call.started",
  "sessionId": "uuid",
  "scenario": {
    "id": "vehicle_theft",
    "title": "Vehicle Theft",
    "category": "Police",
    "description": "Report a recently stolen vehicle.",
    "difficulty": "Medium"
  }
}
```

### Micrófono, procesamiento y reproducción

```json
{ "event": "operator.speaking", "value": true }
```

```json
{ "event": "dispatcher.speaking", "value": true }
```

```json
{
  "event": "engine.activity",
  "message": "Loading speech recognition and transcribing…"
}
```

`engine.activity.message` debe ser `null` cuando termina la actividad. Los
eventos `*.speaking` deben volver a `false` incluso cuando ocurra un error.

### Transcripción

```json
{
  "event": "transcript.operator",
  "text": "My vehicle was stolen.",
  "seconds": 18
}
```

```json
{
  "event": "transcript.dispatcher",
  "text": "What is the vehicle description?",
  "seconds": 21
}
```

### Finalización

```json
{
  "event": "session.completed",
  "session": {
    "id": "uuid",
    "scenario_id": "vehicle_theft",
    "difficulty": "Medium",
    "language": "English",
    "training_type": "Police",
    "started_at": "2026-08-19T01:00:00Z",
    "ended_at": "2026-08-19T01:05:00Z",
    "status": "completed",
    "transcript": [
      { "role": "dispatcher", "text": "911, what is your emergency?", "seconds": 0 }
    ],
    "evaluation": {
      "overall_score": 85,
      "category_scores": { "Accuracy": 90 },
      "collected": ["Vehicle description"],
      "missing": ["License plate"],
      "strengths": ["Clear communication"],
      "improvements": ["Confirm caller phone number"],
      "summary": "Good call with one missing detail."
    }
  }
}
```

## 6. Orden mínimo de eventos

Una llamada correcta debe respetar esta secuencia:

```text
call.start
  → call.status(connecting)
  → call.started
  → call.status(connected)
  → transcript.dispatcher
  → dispatcher.speaking(true/false)

recording.start
  → operator.speaking(true)

recording.stop
  → operator.speaking(false)
  → call.status(processing)
  → engine.activity(...)
  → transcript.operator
  → transcript.dispatcher
  → dispatcher.speaking(true/false)
  → engine.activity(null)
  → call.status(connected)

call.end
  → call.status(completed)
  → session.completed
```

## 7. Errores

Un error controlado debe conservar la conexión:

```json
{
  "event": "error",
  "message": "No speech was detected. Please try again.",
  "recoverable": true
}
```

Una degradación que permite continuar usa:

```json
{
  "event": "warning",
  "message": "The transcript is available, but audio playback failed."
}
```

Requisitos:

- Mensajes aptos para usuarios; los logs técnicos permanecen en el servidor.
- No dejar la sesión en `processing` después de un error recuperable.
- Cerrar el micrófono y restablecer indicadores en bloques de limpieza.
- Rechazar comandos inválidos con `error`, no cerrando el WebSocket.

## 8. Seguridad y despliegue

- Las claves de Anthropic y de cualquier proveedor pertenecen al backend.
- Nunca exponer secretos mediante variables `VITE_*`.
- Escuchar solo en `127.0.0.1` para la modalidad local.
- Para una modalidad remota: `wss://`, autenticación de corta duración,
  autorización por usuario, límites de tamaño/frecuencia y validación de
  `Origin`.
- Validar todos los campos y limitar texto, duración de audio y tamaño de
  historial.
- No enviar rutas locales, stack traces ni contenido de variables de entorno.

## 9. Login y REST (Fase 2)

Además del WebSocket, el backend expone REST para autenticación y los 2 dominios que no son
tiempo real (escenarios, ajustes). El historial y la lista de escenarios para el picker de la
llamada siguen siendo los comandos WS existentes (`scenarios.list`/`history.list`) — REST solo
cubre login y mutaciones (crear/editar/borrar).

```
POST /auth/login   { supervisor_id, passphrase } → { session_id, token }
GET    /scenarios              (Authorization: Bearer <token>)
GET    /scenarios/{id}
POST   /scenarios              { title, category, difficulty, language, description, briefing,
                                  critical_data_points: [{ key, label, required }] }
PUT    /scenarios/{id}         (mismo body que POST)
DELETE /scenarios/{id}
GET    /settings                → { tts_voice }
PUT    /settings                { tts_voice }
```

Todos los endpoints salvo `/health` y `/auth/login` requieren `Authorization: Bearer <token>`
con el token emitido por `/auth/login`. El historial (`history.data`) siempre se escopea
server-side por el `supervisor_id` del token verificado — nunca por un id que mande el cliente
(visibilidad self-only, NFR-06).

## 10. Criterios de aceptación

- [ ] Conexión y reconexión funcionan sin reiniciar el frontend.
- [ ] `system.ping`, escenarios e historial responden con los esquemas exactos.
- [ ] Una llamada completa respeta el orden de eventos documentado.
- [ ] Micrófono y TTS restablecen sus indicadores también ante errores.
- [ ] `session.completed` incluye evaluación e historial persistible.
- [ ] Los errores recuperables mantienen abierto el WebSocket.
- [ ] Ningún secreto aparece en frames, logs del cliente o bundle frontend.
- [ ] El contrato se prueba con casos válidos, comandos desconocidos y campos
      ausentes.
