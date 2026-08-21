# Estado de Fase 1 — seguimiento técnico

Este documento rastrea el checklist de cierre de
[Fase 1 del roadmap](../designs/roadmap-3-fases.md#fase-1--el-loop-de-llamada-en-vivo-como-producto-real)
punto por punto. No duplica el roadmap (que describe qué se quiere) ni TODOS.md (que rastrea
decisiones pendientes) — este archivo dice, para cada ítem de Fase 1, si hoy está `DONE`,
`IN PROGRESS`, o `BLOCKED` (y por qué), con la evidencia (archivo/ADR/test) que lo respalda. Se
actualiza en cada sesión de trabajo sobre Fase 1, no se reescribe desde cero.

**Última actualización:** 2026-08-19 (sesión 5 — cierre del gap técnico durante la
implementación de [Fase 2](../designs/roadmap-3-fases.md#fase-2--los-dominios-de-producto-completos-escenarios-métricas-historial),
ver [PHASE2-PROGRESS.md](./PHASE2-PROGRESS.md)).

## Hito de cierre de Fase 1 (roadmap)

> Un supervisor sostiene una llamada de práctica completa en tiempo real contra un escenario
> configurable (sin editor de UI todavía), con manejo de error real, y la sesión queda
> registrada — sin puntaje/ponderado todavía.

**Estado técnico: DONE** (ver sesión 5 abajo) — el frontend Electron existe y el servidor real
invoca STT/Claude/TTS de verdad sobre el protocolo que ese frontend ya esperaba (antes solo
sincronizaba eventos de la máquina de estados de turno). **El hito de fase completo sigue sin
poder declararse cerrado en sentido estricto** porque depende también de bloqueantes
organizacionales que ningún cambio de código resuelve por sí solo — ver "Bloqueantes
organizacionales" al final. TODO-04 (retención/visibilidad) se resolvió a medias en la sesión 5
(visibilidad sí, retención no); el resto (TODO-03/05/06/07/08) sigue sin evidencia de estar
resuelto.

## Backend / arquitectura

| Ítem del roadmap | Estado | Evidencia |
|---|---|---|
| Harness de tests real ANTES de tocar el rewrite | **DONE** (nivel prototipo) | pytest en `apps/voice-agent/pytest.ini` + `src/test_*.py` (34 tests): unitarios con I/O mockeado para STT/TTS/LLM/micrófono/persistencia/auth/state machine, integración con stub de Claude, test de caos con error de Claude inyectado a mitad de turno. Incluye el fix del bug de `test_microphone.py` (`duration` no existía en `MicrophoneRecorder.record()` — ahora sí, ver `audio/microphone.py`). |
| Puertos/adaptadores formalizados (base para el rewrite) | **DONE** | `core/ports.py` (ADR-0006) — `MicrophonePort`, `SpeechToTextPort`, `TextToSpeechPort`, `DispatcherPort`, `PersistencePort`, `SessionTokenPort`, `DispatcherError`, `InvalidSessionTokenError`. `core/conversation.py` ya solo importa puertos, no adaptadores concretos. |
| Manejo de error de Claude API como estado de primera clase | **DONE (sesión 5)** | `llm/claude.py`: reintento acotado ante errores transitorios (`APIConnectionError`, `APITimeoutError`, `RateLimitError`, `InternalServerError`, `OverloadedError`), `DispatcherError` si se agotan. `server/app.py::get_dispatcher_reply` ahora corre esto en el servidor async real (vía `asyncio.to_thread` + `asyncio.wait_for(CLAUDE_TIMEOUT_SECONDS)`) — recuperación en el propio diálogo (`DISPATCHER_RECOVERY_LINE`) tanto ante `DispatcherError` como ante timeout, sin tumbar la sesión. Probado en `test_server_app.py::test_dispatcher_error_recovers_in_dialogue_instead_of_dropping_the_call`. |
| Motor de persistencia — "la sesión queda registrada" | **DONE (sesión 5, con transcript real)** | `persistence/sqlite_store.py::SQLiteSessionStore` (ADR-0007) guarda un `SessionRecord` completo (transcript real, evaluación, outcome) al terminar o desconectar cualquier sesión, en cualquier estado. Probado de punta a punta en `test_server_app.py::test_full_call_flow_produces_a_completed_session_with_evaluation` y `test_disconnecting_mid_call_persists_a_network_drop_outcome_without_scoring`. **Sigue sin guardar audio** — a propósito, ver NFR-07 (cumplimiento regulatorio de grabación, sin resolver) en [PHASE2-PROGRESS.md](./PHASE2-PROGRESS.md). |
| Auth por sesión (NFR-04) | **DONE** (mecanismo + scope por conexión) | `auth/session_token.py::HmacSessionTokenIssuer` (ADR-0008) + `server/app.py`: `POST /auth/login` emite el token, el handshake de WebSocket lo valida y rechaza (código WS 1008) tanto un token inválido/expirado como uno que no corresponde al `session_id` de la URL — NFR-04 ("una conexión no puede apuntar a la sesión de otra") probado explícitamente en `test_server_app.py::test_websocket_rejects_token_for_a_different_session`. **Falta:** WSS/TLS (NFR-05, ver fila siguiente) y credenciales reales por supervisor — hoy es una passphrase compartida (`SUPERVISOR_PASSPHRASE`), no una cuenta por persona; ver Options not chosen de ADR-0008 si aparece un SSO real. |
| State machine de turnos explícito (listening/hablando/procesando/etc.) | **DONE** (dominio) + **conectada al servidor** | `core/turn_state.py::TurnStateMachine`, cableada en `server/app.py` a eventos JSON entrantes por WebSocket (`{"event": "..."}`) con la respuesta de nuevo estado o de error sin cerrar la conexión (NFR-02). Probado en `test_turn_state.py` y `test_server_app.py`. **Falta:** hoy los eventos de turno los dispara quien sea que hable el protocolo WebSocket a mano (o un test) — todavía no hay VAD real disparándolos desde audio de micrófono. |
| Core async de servidor (FastAPI/WebSocket) | **DONE** (esqueleto: login + handshake + turnos + registro) | `server/app.py::create_app` (factory) + `server_main.py` (entry point real con `uvicorn`). Se agregaron `fastapi`/`uvicorn[standard]` como dependencias (`uv add`, ver `pyproject.toml`/`uv.lock`). 8 tests de integración contra `TestClient` en `test_server_app.py`, sin mocks de bajo nivel — ejercita la app ASGI real. |
| Pipeline de audio real (VAD → chunks → STT/TTS) sobre la conexión | **DONE (sesión 5) — sin VAD automático, a propósito** | `server/app.py::session_socket` ahora invoca `MicrophoneRecorder`/`WhisperSTT`/`ClaudeDispatcher`/`KokoroTTS` reales (vía `asyncio.to_thread`) en el flujo `call.start`/`recording.start`/`recording.stop`/`call.end`, hablando el protocolo completo de comandos/eventos que el frontend ya esperaba — no solo sincronizando `TurnState` como antes. El usuario confirmó explícitamente mantener `recording.start`/`recording.stop` como comandos explícitos (push-to-talk) en vez de VAD automático (ADR-0005 sigue sin implementarse) — no se inventó un protocolo de audio binario/streaming; sigue siendo el modelo "backend en la misma máquina que el mic" de `frontend/BACKEND_REQUIREMENTS.md` §2. Ver [PHASE2-PROGRESS.md](./PHASE2-PROGRESS.md). |
| Confianza de STT por segmento + confirmación de datos críticos (NFR-09) | **DONE** (versión mínima, sin UI) | `stt/whisper.py::WhisperSTT`: segmentos con `avg_logprob` bajo el umbral se marcan inline como `[unclear: ...]` (`test_stt.py`, incluye el fixture de VIN poco claro). `llm/claude.py`: el system prompt instruye al dispatcher a pedir confirmación explícita de un dato crítico marcado así, en vez de aceptarlo en silencio (`test_claude_dispatcher.py::test_respond_system_prompt_instructs_confirming_unclear_critical_data`). **Falta:** esto depende de que el LLM realmente siga la instrucción (no hay garantía dura de modelo) y de que la UI del cliente refleje esa confirmación visualmente — hoy es solo comportamiento de diálogo. |
| WSS/TLS (NFR-05) | **DONE** (certificado autofirmado, prendido por default) | `server/tls.py::ensure_self_signed_cert` genera cert+key si no existen (idempotente — no se regenera en cada arranque). `server_main.py::build_uvicorn_kwargs` los pasa a `uvicorn.run` por default; `DISABLE_TLS=1` es el escape hatch explícito solo para desarrollo local. Probado en `test_server_tls.py` y `test_server_main.py`. **Falta:** esto es un cert autofirmado — cada máquina de supervisor necesita confiar en él una vez (paso operativo, ver TODO-03), o alguien pone un reverse proxy con un cert real delante. (Sesión 5: el cliente Electron ahora confía en cualquier cert inválido vía `certificate-error` para poder hablarle a este cert autofirmado — ver `frontend/electron/main.cjs` y su comentario sobre el trade-off de seguridad; el endurecimiento correcto es fijar el fingerprint específico, no aceptar cualquiera.) |
| Logging estructurado con correlation id | **DONE (sesión 5)** | `core/observability.py` (JSON por línea, `log_event` con `correlation_id` explícito) cableado en `server/app.py`: `login_succeeded`/`login_failed`, `session_connected`, `turn_transition`/`turn_transition_rejected`, `stt_completed`/`stt_failed` (con `latency_ms` y `low_confidence_segment_count`), `dispatcher_completed`/`dispatcher_error` (con `latency_ms`), `tts_completed`/`tts_failed` (con `latency_ms`), `session_disconnected`. Probado en `test_observability.py` y de punta a punta en `test_server_app.py::test_server_emits_structured_logs_with_session_correlation_id`. NFR-08 queda cubierto: la latencia/confianza de STT y la latencia de Claude/TTS que antes no había nada real que instrumentar, ahora sí. |

## Frontend (Electron + React + Tailwind)

**DONE (sesión 5, cierra Fase 1 + integra Fase 2)** — existe un proyecto Electron+React+Zustand
completo en `frontend/` (sin Tailwind real pese al nombre del ADR-0002 — es CSS a mano en
`src/styles/globals.css`, decisión previa a esta sesión, no se introdujo Tailwind de forma no
solicitada). Cubre: indicador visual de turno con sus estados (`CallPage.tsx` — conectando/
chequeo de mic, procesando, hablando, pausado, corte de conexión), estado de conexión/
reconexión (`voiceBridge.ts` con reconexión automática), control de pausa/abortar, transición de
decompresión (pantalla de resultado con `SessionBreakdown`, no un corte instantáneo), y
mecanismo de escenario intercambiable con biblioteca completa (ya con editor CRUD, ver
[PHASE2-PROGRESS.md](./PHASE2-PROGRESS.md) — el roadmap solo pedía "sin editor" para el cierre
de Fase 1, el editor llegó junto con Fase 2 en la misma sesión). El prototipo CLI actual sigue
funcionando como fallback manual (NFR-03) — no se tocó su comportamiento por defecto.
**Falta que no bloquea el hito:** el login del frontend (`LoginPage.tsx`) es nuevo y no tiene
todavía un test automatizado (no existe framework de test de frontend en el repo, ver
[PHASE2-PROGRESS.md](./PHASE2-PROGRESS.md) para ese gap conocido).

## Bloqueantes organizacionales (ningún cambio de código los resuelve)

Ver [TODOS.md](./TODOS.md) para el detalle completo. Sin resolver a la fecha de esta
actualización:

- **TODO-03** — dueño operativo de la caja RTX. Sin nombre.
- **TODO-04** — política de retención/visibilidad del historial. **Visibilidad resuelta**
  (self-only, sesión 5) — **retención sigue sin resolver.**
- **TODO-05** — cumplimiento regulatorio de grabación de voz. Sin confirmar.
- **TODO-06** — segundo ingeniero/revisor nombrado. Sin nombre.
- **TODO-07** — presupuesto de capital para la GPU RTX. Sin confirmar.
- **TODO-08** — resultado del spike de Gate 0 (Fase 0). Sin evidencia de que se haya corrido.

El roadmap marca estos ítems como bloqueantes explícitos de Fase 1, no como "nice to have" —
ver la sección "Organizacional (bloqueante, no técnico)" del
[roadmap](../designs/roadmap-3-fases.md#fase-1--el-loop-de-llamada-en-vivo-como-producto-real).
El hito de cierre de fase no se puede marcar `DONE` solo con trabajo de código mientras estos
sigan `PENDING`.

## Sesión 6 (2026-08-20) — Gate 0 + primera corrida de punta a punta real

Primera vez que este proyecto corre contra hardware/API real de punta a punta (hasta ahora todo
`test_server_app.py` usaba stubs de STT/TTS/LLM/mic, ver "Verificación" abajo).

- **Gate 0 (TODO-08): spike de latencia corrido, resultado real documentado en
  [TODOS.md#todo-08](./TODOS.md#todo-08).** NFR-01 **no se cumple** hoy: 5622ms de media medida
  (objetivo <1500ms) en la máquina confirmada por el usuario como la caja RTX candidata (RTX
  3050 6GB). Hallazgo adicional: `torch.cuda.is_available()` es `False` en este entorno —
  Whisper/Kokoro corrieron 100% en CPU pese a la GPU física, por falta del runtime de CUDA
  (`cublas64_12.dll`), no por config. Faltan todavía el spike de red con una segunda máquina y
  el user-test de 2-3 supervisores reales — TODO-08 queda `IN PROGRESS`, no `RESOLVED`.
- **TODO-09 (causa raíz), TODO-03 (dueño de la caja), TODO-04 (retención), TODO-05
  (cumplimiento regulatorio) resueltos por decisión del usuario** — ver el detalle y las
  actualizaciones de cada uno en [TODOS.md](./TODOS.md).
- **3 bugs reales de crash encontrados y corregidos, los tres de la misma familia** (emoji en un
  `print()` + consola de Windows en codepage `cp1252`, que no puede codificarlos):
  - `server_main.py::build_uvicorn_kwargs` — crasheaba **antes de arrancar uvicorn** en el
    escape hatch `DISABLE_TLS=1` que la propia documentación recomienda para desarrollo local.
  - `audio/microphone.py::_save` — crasheaba dentro de `stop_recording()`, y el servidor lo
    capturaba como *"No speech was detected"*, enmascarando un crash real como un problema de
    voz del supervisor (encontrado en vivo, durante la corrida real de abajo).
  - `core/conversation.py` (4 sitios) — el prototipo CLI, fallback de NFR-03, tenía el mismo
    problema — el fallback manual tampoco funcionaba en Windows hasta este fix.
- **Primera llamada de punta a punta real** (servidor real `server_main.py` con
  Whisper+Claude+Kokoro+mic reales, sin stubs; frontend real vía navegador contra el mismo
  backend; voz real del usuario, no un fixture): 2 turnos reales completos, transcript real,
  respuesta real de Claude en personaje, TTS real reproducido, sesión persistida con score real.
  Cierra el punto pendiente que esta misma sección pedía en la sesión 5 ("una llamada real de
  punta a punta... no disponible en este entorno").
- **Hallazgo de la llamada real, no un bug de crash sino de precisión del scoring:** ver
  [TODO-17](./TODOS.md#todo-17) — la heurística de completitud no reconoció datos que el
  operador sí comunicó correctamente (descripción del vehículo, ubicación, tiempo aproximado),
  solo por no repetir el texto literal del label del dato. Documentado con la evidencia real
  exacta (transcript + scores), no como sospecha.

## Próxima sesión de trabajo (sugerido, no comprometido)

**Nota (sesión 5):** los 4 ítems que este documento sugería antes de la sesión 5 ya están
resueltos (frontend existente y ahora cableado al protocolo real, timeout de Claude, logging de
latencia) — ver [PHASE2-PROGRESS.md](./PHASE2-PROGRESS.md) para el detalle. Lo que queda:

1. **Actualizado en sesión 6:** el spike de latencia de Gate 0 (TODO-08) ya corrió con resultado
   real — NFR-01 no se cumple hoy, ver la sección de sesión 6 arriba y
   [TODOS.md#todo-08](./TODOS.md#todo-08). Falta todavía el spike de red con una segunda
   máquina y el user-test con 2-3 supervisores reales antes de poder cerrar TODO-08 del todo.
   Repara el runtime de CUDA en este entorno (falta `cublas64_12.dll`) y re-mide con GPU real
   antes de tomar cualquier decisión definitiva sobre ADR-0004 a partir de estos números.
2. Instalar el certificado autofirmado en el almacén de confianza real de las máquinas de
   supervisor (o poner un reverse proxy con cert real) — el cliente Electron hoy confía en
   cualquier cert como parche temporal (`frontend/electron/main.cjs`), no es la solución final.
3. Retención (la mitad de TODO-04 que sigue pendiente) — cuánto tiempo se guardan transcripts,
   mecanismo de purga por antigüedad.
4. Framework de test de frontend (no existe ninguno hoy) — `LoginPage.tsx`, el editor de
   escenarios y el historial nuevos no tienen cobertura automatizada todavía, solo verificación
   manual + `tsc --noEmit`/`vite build` en verde.

## Historial de sesiones de trabajo

- **2026-08-19 (sesión 1):** harness de tests, puertos formalizados, manejo de error de Claude
  como estado de primera clase (versión mínima), ADR-0007 y ADR-0008 propuestos y aceptados por
  el usuario, adaptadores de persistencia (SQLite) y auth (token HMAC) implementados y probados,
  state machine de turnos implementada y probada — todo en aislamiento, sin servidor real
  todavía (NFR-10 al pie de la letra: "tests antes del rewrite").
- **2026-08-19 (sesión 2, misma fecha, iteración siguiente del loop):** servidor FastAPI/
  WebSocket real (`server/app.py` + `server_main.py`) cableando las piezas de la sesión 1 —
  login, handshake autenticado con scope por sesión (NFR-04), sincronización de eventos de
  turno, registro de sesión al desconectar. Se agregaron `fastapi`/`uvicorn[standard]` como
  dependencias nuevas (`uv add`). 42 tests en total, todos verdes. Se decidió explícitamente
  NO inventar el protocolo de audio binario (chunk/VAD) sin el dato del spike de Gate 0 — ver
  la fila "Pipeline de audio real" arriba.
- **2026-08-19 (sesión 3, misma fecha, siguiente iteración):** WSS/TLS (NFR-05) —
  `server/tls.py` genera un certificado autofirmado idempotente, `server_main.py` lo usa por
  default (`DISABLE_TLS=1` como escape hatch explícito de desarrollo). Se agregó `cryptography`
  como dependencia nueva (`uv add`). Se agregó `.gitignore` para `server.crt`/`server.key`/
  `sessions.db` (nunca committear una clave privada o la base de sesiones). 49 tests en total,
  todos verdes. **Nota:** se encontró `apps/voice-agent/recording.wav` borrado en el working
  tree (aparece como `D` en `git status`) sin que ningún comando de esta sesión lo haya tocado
  — reportado al usuario, no se restauró unilateralmente. También se confirmó que un hook de
  gstack (`gstack-timeline-stop`) auto-commitea y pushea a `origin/master` al final de cada
  turno — comportamiento esperado, confirmado por el usuario.
- **2026-08-19 (sesión 4, misma fecha, siguiente iteración):** logging estructurado (NFR-08) —
  `core/observability.py` (JSON por línea + `log_event` con `correlation_id` explícito),
  cableado en `server/app.py` en las 4 etapas del ciclo de vida de una conexión (login, connect,
  cada turno, disconnect). 54 tests en total, todos verdes. Sin dependencias nuevas.
- **2026-08-19 (sesión 5, implementación de Fase 2):** cierre del gap técnico real de Fase 1
  (servidor reescrito para invocar STT/Claude/TTS de verdad y hablar el protocolo completo que
  el frontend Electron ya esperaba) + los 3 dominios de producto de Fase 2 (escenarios, métricas,
  historial) + ajustes + pulido del loop en vivo. Ver [PHASE2-PROGRESS.md](./PHASE2-PROGRESS.md)
  para el detalle completo. 89 tests de backend en total, todos verdes; frontend con
  `tsc --noEmit` y `vite build` en verde (no hay framework de test de frontend en el repo
  todavía).
- **2026-08-20 (sesión 6):** Gate 0 (spike de latencia real, resultado documentado) + primera
  corrida de punta a punta contra hardware/API real (Whisper+Claude+Kokoro+mic reales, voz real
  del usuario) + 3 bugs de crash por encoding en Windows encontrados y corregidos
  (`server_main.py`, `audio/microphone.py`, `core/conversation.py`) + fix de CORS en
  `server/app.py` (encontrado en la sesión anterior de conexión frontend-backend) + TODO-03,
  TODO-04, TODO-05, TODO-09 resueltos por decisión del usuario + TODO-17 nuevo (heurística de
  completitud no reconoce habla natural real, con evidencia). Ver la sección de sesión 6 arriba
  para el detalle completo. 106 tests de backend en total, todos verdes.
