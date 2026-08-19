# Estado de Fase 1 — seguimiento técnico

Este documento rastrea el checklist de cierre de
[Fase 1 del roadmap](../designs/roadmap-3-fases.md#fase-1--el-loop-de-llamada-en-vivo-como-producto-real)
punto por punto. No duplica el roadmap (que describe qué se quiere) ni TODOS.md (que rastrea
decisiones pendientes) — este archivo dice, para cada ítem de Fase 1, si hoy está `DONE`,
`IN PROGRESS`, o `BLOCKED` (y por qué), con la evidencia (archivo/ADR/test) que lo respalda. Se
actualiza en cada sesión de trabajo sobre Fase 1, no se reescribe desde cero.

**Última actualización:** 2026-08-19.

## Hito de cierre de Fase 1 (roadmap)

> Un supervisor sostiene una llamada de práctica completa en tiempo real contra un escenario
> configurable (sin editor de UI todavía), con manejo de error real, y la sesión queda
> registrada — sin puntaje/ponderado todavía.

**Estado global: BLOCKED.** No solo por trabajo técnico pendiente (backend async, VAD, cliente
Electron, persistencia — todo abajo) sino por bloqueantes organizacionales que ningún cambio de
código puede resolver por sí solo — ver la sección "Bloqueantes organizacionales" al final. El
gate de Fase 0 (spike de validación) tampoco está confirmado como corrido — ver
[TODO-08](./TODOS.md#todo-08).

## Backend / arquitectura

| Ítem del roadmap | Estado | Evidencia |
|---|---|---|
| Harness de tests real ANTES de tocar el rewrite | **DONE** (nivel prototipo) | pytest en `apps/voice-agent/pytest.ini` + `src/test_*.py` (34 tests): unitarios con I/O mockeado para STT/TTS/LLM/micrófono/persistencia/auth/state machine, integración con stub de Claude, test de caos con error de Claude inyectado a mitad de turno. Incluye el fix del bug de `test_microphone.py` (`duration` no existía en `MicrophoneRecorder.record()` — ahora sí, ver `audio/microphone.py`). |
| Puertos/adaptadores formalizados (base para el rewrite) | **DONE** | `core/ports.py` (ADR-0006) — `MicrophonePort`, `SpeechToTextPort`, `TextToSpeechPort`, `DispatcherPort`, `PersistencePort`, `SessionTokenPort`, `DispatcherError`, `InvalidSessionTokenError`. `core/conversation.py` ya solo importa puertos, no adaptadores concretos. |
| Manejo de error de Claude API como estado de primera clase | **IN PROGRESS** (versión mínima) | `llm/claude.py`: reintento acotado ante errores transitorios (`APIConnectionError`, `APITimeoutError`, `RateLimitError`, `InternalServerError`, `OverloadedError`), `DispatcherError` si se agotan. `core/conversation.py`: recuperación en el propio diálogo (`DISPATCHER_RECOVERY_LINE`). **Falta:** timeout configurable explícito (hoy depende del timeout default del SDK de Anthropic), y esto todavía corre en el prototipo CLI síncrono, no en el servidor async real. |
| Motor de persistencia — "la sesión queda registrada" | **DONE** (a nivel servidor de eventos de turno) | `persistence/sqlite_store.py::SQLiteSessionStore` (ADR-0007) ya lo llama el servidor real: `server/app.py` guarda un `SessionRecord` al desconectar cualquier WebSocket de sesión, en cualquier estado. Probado de punta a punta en `test_server_app.py::test_disconnecting_persists_the_session_record`. **Falta:** hoy graba eventos de turno, no todavía transcripciones/audio de la llamada real (eso llega con el pipeline de audio real, ver abajo). |
| Auth por sesión (NFR-04) | **DONE** (mecanismo + scope por conexión) | `auth/session_token.py::HmacSessionTokenIssuer` (ADR-0008) + `server/app.py`: `POST /auth/login` emite el token, el handshake de WebSocket lo valida y rechaza (código WS 1008) tanto un token inválido/expirado como uno que no corresponde al `session_id` de la URL — NFR-04 ("una conexión no puede apuntar a la sesión de otra") probado explícitamente en `test_server_app.py::test_websocket_rejects_token_for_a_different_session`. **Falta:** WSS/TLS (NFR-05, ver fila siguiente) y credenciales reales por supervisor — hoy es una passphrase compartida (`SUPERVISOR_PASSPHRASE`), no una cuenta por persona; ver Options not chosen de ADR-0008 si aparece un SSO real. |
| State machine de turnos explícito (listening/hablando/procesando/etc.) | **DONE** (dominio) + **conectada al servidor** | `core/turn_state.py::TurnStateMachine`, cableada en `server/app.py` a eventos JSON entrantes por WebSocket (`{"event": "..."}`) con la respuesta de nuevo estado o de error sin cerrar la conexión (NFR-02). Probado en `test_turn_state.py` y `test_server_app.py`. **Falta:** hoy los eventos de turno los dispara quien sea que hable el protocolo WebSocket a mano (o un test) — todavía no hay VAD real disparándolos desde audio de micrófono. |
| Core async de servidor (FastAPI/WebSocket) | **DONE** (esqueleto: login + handshake + turnos + registro) | `server/app.py::create_app` (factory) + `server_main.py` (entry point real con `uvicorn`). Se agregaron `fastapi`/`uvicorn[standard]` como dependencias (`uv add`, ver `pyproject.toml`/`uv.lock`). 8 tests de integración contra `TestClient` en `test_server_app.py`, sin mocks de bajo nivel — ejercita la app ASGI real. |
| Pipeline de audio real (VAD → chunks → STT/TTS) sobre la conexión | **NOT STARTED — a propósito** | El servidor de arriba sincroniza *eventos de turno* como JSON, no audio binario. El formato de chunk, dónde vive el VAD, y el tamaño de buffer dependen del resultado del spike de latencia de Gate 0 (TODO-08) — no hay ADR de protocolo de audio todavía, e inventar uno sin ese dato violaría la regla ADR-first de CONTRIBUTING.md. Ver el docstring de `server/app.py` para el razonamiento completo. |
| Confianza de STT por segmento + confirmación de datos críticos (NFR-09) | **DONE** (versión mínima, sin UI) | `stt/whisper.py::WhisperSTT`: segmentos con `avg_logprob` bajo el umbral se marcan inline como `[unclear: ...]` (`test_stt.py`, incluye el fixture de VIN poco claro). `llm/claude.py`: el system prompt instruye al dispatcher a pedir confirmación explícita de un dato crítico marcado así, en vez de aceptarlo en silencio (`test_claude_dispatcher.py::test_respond_system_prompt_instructs_confirming_unclear_critical_data`). **Falta:** esto depende de que el LLM realmente siga la instrucción (no hay garantía dura de modelo) y de que la UI del cliente refleje esa confirmación visualmente — hoy es solo comportamiento de diálogo. |
| WSS/TLS (NFR-05) | **DONE** (certificado autofirmado, prendido por default) | `server/tls.py::ensure_self_signed_cert` genera cert+key si no existen (idempotente — no se regenera en cada arranque). `server_main.py::build_uvicorn_kwargs` los pasa a `uvicorn.run` por default; `DISABLE_TLS=1` es el escape hatch explícito solo para desarrollo local. Probado en `test_server_tls.py` y `test_server_main.py`. **Falta:** esto es un cert autofirmado — cada máquina de supervisor necesita confiar en él una vez (paso operativo, ver TODO-03), o alguien pone un reverse proxy con un cert real delante. Con esto, el gate de AGENTS.md regla 5 (auth + WSS/TLS) queda técnicamente cumplido — el spike de Gate 0 y el resto de bloqueantes organizacionales siguen sin resolver aparte. |
| Logging estructurado con correlation id | **IN PROGRESS** | `core/observability.py` (JSON por línea, `log_event` con `correlation_id` explícito) cableado en `server/app.py`: `login_succeeded`/`login_failed`, `session_connected`, `turn_transition`/`turn_transition_rejected`, `session_disconnected` (con `duration_seconds`/`turn_count`). Probado en `test_observability.py` y de punta a punta en `test_server_app.py::test_server_emits_structured_logs_with_session_correlation_id` (mismo `correlation_id` en las 4 etapas). **Falta:** latencia/confianza de STT y latencia de Claude — NFR-08 pide instrumentar esas etapas también, pero el servidor todavía no invoca STT/TTS/Claude (ver fila "Pipeline de audio real"), así que no hay nada real que instrumentar ahí todavía. |

## Frontend (Electron + React + Tailwind)

**NOT STARTED en su totalidad.** No existe todavía ningún proyecto Electron en el repo — hoy
solo hay un prototipo CLI en Python (`apps/voice-agent/src/main.py`). Esto es la porción más
grande de trabajo técnico restante de Fase 1: indicador visual de turno con todos sus estados,
estado de conexión/reconexión, control de pausa/abortar, transición de decompresión, mecanismo
de escenario intercambiable (sin editor todavía). El prototipo CLI actual sigue funcionando como
fallback manual (NFR-03) — no se tocó su comportamiento por defecto, solo se le agregaron
puertos y manejo de error por debajo.

## Bloqueantes organizacionales (ningún cambio de código los resuelve)

Ver [TODOS.md](./TODOS.md) para el detalle completo. Sin resolver a la fecha de esta
actualización:

- **TODO-03** — dueño operativo de la caja RTX. Sin nombre.
- **TODO-04** — política de retención/visibilidad del historial. Sin resolver.
- **TODO-05** — cumplimiento regulatorio de grabación de voz. Sin confirmar.
- **TODO-06** — segundo ingeniero/revisor nombrado. Sin nombre.
- **TODO-07** — presupuesto de capital para la GPU RTX. Sin confirmar.
- **TODO-08** — resultado del spike de Gate 0 (Fase 0). Sin evidencia de que se haya corrido.

El roadmap marca estos ítems como bloqueantes explícitos de Fase 1, no como "nice to have" —
ver la sección "Organizacional (bloqueante, no técnico)" del
[roadmap](../designs/roadmap-3-fases.md#fase-1--el-loop-de-llamada-en-vivo-como-producto-real).
El hito de cierre de fase no se puede marcar `DONE` solo con trabajo de código mientras estos
sigan `PENDING`.

## Próxima sesión de trabajo (sugerido, no comprometido)

1. Decidir dónde empieza el proyecto Electron+React+Tailwind (repo nuevo dentro de `apps/`,
   estructura de carpetas, gestor de paquetes) — todavía no existe ni un scaffold, y es la
   porción más grande de trabajo técnico que queda en Fase 1. Requiere decisiones de tooling
   (npm/pnpm, Vite, TypeScript o no) que no están fijadas en ningún ADR todavía — candidato a
   confirmar con el usuario antes de generar la estructura, no a asumir en silencio.
2. Confirmar si el spike de Gate 0 (TODO-08) ya corrió fuera de este repo o sigue pendiente —
   condiciona si el protocolo de audio real (chunk size, punto de VAD) se puede empezar a
   diseñar, y si ADR-0004 (servidor LAN) sigue siendo la base correcta.
3. Timeout configurable explícito en `ClaudeDispatcher` (hoy depende del default del SDK) —
   cierra del todo la fila "Manejo de error de Claude API" de la tabla de arriba.
4. Cuando exista el pipeline de audio real: extender `log_event` a STT/Claude/TTS (latencia,
   confianza por segmento) — `core/observability.py` ya está listo para eso, solo falta algo
   real que instrumentar.

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
