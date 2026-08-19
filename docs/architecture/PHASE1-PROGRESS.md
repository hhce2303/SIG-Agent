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
| Motor de persistencia — "la sesión queda registrada" | **IN PROGRESS** | [ADR-0007](./adr/0007-motor-de-persistencia.md) `accepted`. Adaptador `persistence/sqlite_store.py::SQLiteSessionStore` implementado y probado (`test_persistence.py`) contra `PersistencePort`/`SessionRecord`. **Falta:** nadie lo llama todavía — el server que escriba una sesión real al terminar una llamada no existe aún. |
| Auth por sesión (NFR-04) | **IN PROGRESS** | [ADR-0008](./adr/0008-mecanismo-de-autenticacion-de-sesion.md) `accepted`. Adaptador `auth/session_token.py::HmacSessionTokenIssuer` implementado y probado (`test_auth.py`) contra `SessionTokenPort`. **Falta:** WSS/TLS (NFR-05) y el propio servidor que exija el token en el handshake de WebSocket — el gate de AGENTS.md regla 5 sigue sin cumplirse hasta que exista el servidor real. |
| State machine de turnos explícito (listening/hablando/procesando/etc.) | **DONE** (dominio, sin conectar a I/O real) | `core/turn_state.py::TurnStateMachine` — los 7 estados del roadmap, timeout de `processing` con fallback a la línea de recuperación, recuperación de corte falso, red degradada/desconexión válidas desde cualquier estado no terminal. Probado en `test_turn_state.py`. **Falta:** conectarla a VAD real y a una conexión WebSocket real — hoy es una máquina de estados que nadie alimenta con eventos reales todavía. |
| Core async de servidor (FastAPI/WebSocket) + pipeline de audio Electron | **NOT STARTED** | Reescritura completa, no extensión del prototipo (ver ADR-0006, AGENTS.md). Las piezas de las que depende (persistencia, auth, state machine) ya están construidas y probadas por separado — este ítem es específicamente cablearlas juntas detrás de FastAPI/WebSocket, más VAD real. |
| Confianza de STT por segmento + confirmación de datos críticos (NFR-09) | **NOT STARTED** | `test_stt.py::test_transcribe_unclear_vin_fixture_...` documenta el fixture de VIN poco claro y el comportamiento actual (la confianza no se expone) — sirve de regresión para cuando esto se implemente. |
| WSS/TLS (gate de seguridad, junto con auth) | **NOT STARTED** | Depende de que exista el servidor real — no hay nada que cifrar todavía. |
| Logging estructurado con correlation id + latencia por turno | **NOT STARTED** | Depende del core async de servidor (NFR-08). |

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

1. Núcleo async de servidor (FastAPI/WebSocket): cablear `TurnStateMachine`,
   `SQLiteSessionStore` y `HmacSessionTokenIssuer` (ya construidos y probados) detrás de un
   endpoint WebSocket real, con WSS/TLS.
2. Confirmar si el spike de Gate 0 (TODO-08) ya corrió fuera de este repo o sigue pendiente —
   condiciona si ADR-0004 (servidor LAN) sigue siendo la base correcta para el punto 1.
3. Decidir dónde empieza el proyecto Electron+React+Tailwind (repo nuevo dentro de `apps/`,
   estructura de carpetas, gestor de paquetes) — todavía no existe ni un scaffold.

## Historial de sesiones de trabajo

- **2026-08-19 (sesión 1):** harness de tests (34 tests), puertos formalizados, manejo de error
  de Claude como estado de primera clase (versión mínima), ADR-0007 y ADR-0008 propuestos y
  aceptados por el usuario, adaptadores de persistencia (SQLite) y auth (token HMAC)
  implementados y probados, state machine de turnos implementada y probada. Nada de esto está
  todavía conectado a un servidor real ni a hardware real (mic/RTX) — son piezas de dominio y
  adaptador probadas de forma aislada, siguiendo NFR-10 al pie de la letra ("tests antes del
  rewrite").
