# Estado de Fase 2 — seguimiento técnico

Este documento rastrea el checklist de cierre de
[Fase 2 del roadmap](../designs/roadmap-3-fases.md#fase-2--los-dominios-de-producto-completos-escenarios-métricas-historial)
punto por punto, con el mismo formato que [PHASE1-PROGRESS.md](./PHASE1-PROGRESS.md). No
duplica el roadmap ni [TODOS.md](./TODOS.md) — dice, para cada ítem de Fase 2, si está `DONE`,
`IN PROGRESS`, o `BLOCKED`, con la evidencia que lo respalda.

**Última actualización:** 2026-08-19 (sesión 5, primera y única sesión de esta fase hasta ahora).

## Hito de cierre de Fase 2 (roadmap)

> El ciclo completo que pide el `/goal` original — llamada en vivo + escenario elegido por el
> usuario + auditoría con métricas objetivas al terminar — funciona de punta a punta.

**Estado: DONE de punta a punta contra los adaptadores reales, verificado manualmente pendiente
de correr contra hardware real** (STT/Claude/TTS/mic reales, no solo stubs de test — ver
"Verificación" abajo). Esta sesión también tuvo que cerrar el gap técnico real de Fase 1 (el
servidor no invocaba STT/Claude/TTS y el protocolo no coincidía con el frontend) — sin eso, el
hito de Fase 2 no era alcanzable. Ver [PHASE1-PROGRESS.md](./PHASE1-PROGRESS.md) para ese lado.

**Decisiones de producto resueltas por el usuario antes de construir** (evitando el "trabajo que
se tira" que el design doc advertía si se construía antes de resolver el formato):

1. Editor de escenarios: campos estructurados + narrativa libre (no texto libre puro) —
   resuelve [TODO-11](./TODOS.md#todo-11).
2. Fórmula de métricas: completitud 40% / tiempo-a-dato-crítico 30% / claridad 20% / tiempo
   total 10% — resuelve [TODO-10](./TODOS.md#todo-10).
3. Visibilidad de historial: self-only — resuelve la mitad de [TODO-04](./TODOS.md#todo-04).
4. VAD automático: fuera de alcance, se mantiene push-to-talk explícito — ADR-0005 sigue sin
   implementar de verdad, decisión explícita del usuario, no un olvido.

## Escenarios (editor CRUD)

| Ítem | Estado | Evidencia |
|---|---|---|
| Formato estructurado + narrativa libre | **DONE** | `core/ports.py::Scenario`/`CriticalDataPoint`/`ScenarioPort`. |
| Persistencia + semilla inicial | **DONE** | `persistence/sqlite_scenario_store.py::SQLiteScenarioStore` — siembra `vehicle_theft` (migrado del `SCENARIO` string original), `domestic_dispute`, `traffic_accident` en el primer arranque; no duplica en arranques siguientes. `test_scenarios.py`. |
| CRUD por REST | **DONE** | `GET/POST/PUT/DELETE /scenarios[/{id}]` en `server/app.py`, protegidos por `Authorization: Bearer`. `test_server_app.py::test_scenario_crud_round_trip`. |
| Más de un tipo de incidente | **DONE** | 3 escenarios sembrados (robo de vehículo, disputa doméstica, accidente de tránsito) + CRUD para agregar más. |
| UI del editor (frontend) | **DONE** | `frontend/src/pages/ScenarioEditorPage.tsx` — formulario validado con campos estructurados + lista editable de `critical_data_points` + textarea de briefing. `ScenariosPage.tsx` con Nuevo/Editar. |
| Conexión con el motor de métricas | **DONE** | `server/app.py::call.start` resuelve el escenario completo por id y pasa `critical_data_points` a `score_session` al terminar la llamada — la completitud se calcula contra datos reales del escenario elegido, no un escenario hardcodeado. |

## Motor de métricas/ponderado

| Ítem | Estado | Evidencia |
|---|---|---|
| Fórmula resuelta y configurable | **DONE** | `core/scoring.py::ScoreWeights` (40/30/20/10, override por env `METRICS_WEIGHT_*`). |
| Cálculo de las 4 categorías | **DONE** | `core/scoring.py::score_session` — completitud (keyword matching contra `critical_data_points`), tiempo-a-dato-crítico (banda 60-180s), claridad (ratio de muletillas), tiempo total (banda 90-240s). Dominio puro, sin FastAPI/SQLite. `test_scoring.py` (9 tests). |
| Reloj del servidor como autoridad única | **DONE** | Todos los timestamps de `score_session` vienen de `SessionRecord.started_at`/`ended_at`/transcript `at`, todos poblados por el `clock` inyectado del servidor — nunca un timestamp de cliente. |
| Puntaje compuesto + desglose + narrativa de debrief | **DONE** | `Evaluation` (`overall_score`, `category_scores`, `collected`/`missing`, `strengths`/`improvements` generados por reglas deterministas, `summary`) — mismo shape que el frontend ya esperaba, cero cambios de tipo necesarios en `frontend/src/types.ts`. |
| Puntaje diferenciado: abandono vs. caída de red | **DONE** | `outcome`: `"ended"` (siempre puntuado, incluso temprano/parcial) vs. `"network_drop"` (`score_session` devuelve `None` — sin puntaje punitivo). `test_server_app.py::test_disconnecting_mid_call_persists_a_network_drop_outcome_without_scoring`. |
| UI de desglose (3-4 pantallas del roadmap) | **DONE, como síntesis** | En vez de 3-4 pantallas separadas (que hubieran duplicado el mismo layout), se extrajo `frontend/src/components/SessionBreakdown.tsx` — un componente reusado como pantalla de decompresión post-llamada (`ReviewPage.tsx`) Y como drill-down del historial (`PerformancePage.tsx`). Decisión de síntesis documentada en el componente. |

## Historial de sesiones

| Ítem | Estado | Evidencia |
|---|---|---|
| Modelo de visibilidad real (self-only) | **DONE** | `persistence/sqlite_store.py::list_sessions(supervisor_id)` — siempre escopeado por el `supervisor_id` del token verificado (`server/app.py`), nunca por lo que mande el cliente. `test_persistence.py::test_list_sessions_scopes_by_supervisor_and_orders_newest_first`. |
| Lista/filtro | **DONE** | `frontend/src/pages/PerformancePage.tsx` — filtro por escenario, tabla completa (incluye sesiones `network_drop` marcadas "Not scored", no solo las puntuadas). |
| Comparación de tendencia en el tiempo | **DONE** | Gráfico de `overall_score` en el tiempo (recharts, ya era dependencia). |
| Replay | **DONE, acotado a transcripción** | Drill-down reusa `SessionBreakdown` → timeline de transcripción con timestamps. **No hay replay de audio** — no se captura ni se persiste audio en ningún punto de esta arquitectura, y NFR-07 (cumplimiento regulatorio de grabación) sigue sin resolver ([TODO-05](./TODOS.md#todo-05)); grabar audio real antes de resolver eso sería imprudente. |

## Ajustes

| Ítem | Estado | Evidencia |
|---|---|---|
| Voz de TTS | **DONE** | `core/ports.py::SettingsPort` + `persistence/sqlite_settings_store.py` (una fila global, concurrencia=1). `GET/PUT /settings` REST. `frontend/src/pages/SettingsPage.tsx` — dropdown de voces conocidas de Kokoro. `tts/kokoro.py::KokoroTTS.speak` acepta `voice` por llamada sin recargar el pipeline. |
| Sensibilidad de VAD | **N/A a propósito** | No hay VAD automático implementado (decisión del usuario, ver arriba) — no hay nada que este ajuste controlaría todavía. |

## Pulido del loop en vivo

| Ítem | Estado | Evidencia |
|---|---|---|
| Estado de "conectando/chequeo de mic" | **DONE** | `server/app.py::call.start` emite `call.status(connecting)` + `engine.activity("Checking microphone…")` y hace un chequeo real (`MicrophonePort.is_available`) antes de aceptar la llamada — error recuperable si no hay mic. `test_server_app.py::test_call_start_with_no_microphone_reports_a_recoverable_error`. |
| Pausa/resume | **DONE** | `core/turn_state.py` ganó `TurnState.PAUSED` + eventos `pause_requested`/`resume_requested`. `test_turn_state.py`, `test_server_app.py::test_call_pause_and_resume_update_call_status`. |
| Puntaje diferenciado de sesión incompleta | **DONE** | Ver "Motor de métricas" arriba — mismo mecanismo (`outcome`). |
| Aviso en vivo de caída de red | **DONE** | `frontend/src/pages/CallPage.tsx` — banner derivado de `connection === 'disconnected'` con una llamada activa (no depende de un evento `error` explícito, que no puede llegar si la conexión ya está muerta). |

## Streaming de respuesta de Claude (contingencia, TODO-12)

**No construido — correctamente, no por omisión.** El roadmap lo condiciona explícitamente al
resultado del spike de latencia de Gate 0 (TODO-08), y no hay evidencia de que ese spike se haya
corrido. Construirlo especulativamente violaría tanto la regla ADR-first como la instrucción
explícita de TODO-12 ("no como nota al pie" implica que si se hace, se dimensiona como
workstream propio con evidencia, no que se haga sin ella).

## Cierre del gap técnico de Fase 1 (prerequisito de este trabajo)

Ver [PHASE1-PROGRESS.md](./PHASE1-PROGRESS.md) para el detalle completo. Resumen: `server/app.py`
se reescribió para invocar STT/Claude/TTS reales (antes solo sincronizaba `TurnState` como JSON)
y hablar el protocolo completo de comandos/eventos que el frontend ya esperaba (antes no
coincidían en absoluto — el frontend nunca hacía login ni abría el WS con `session_id`/`token`).
Esto incluyó agregar el flujo de login al frontend (`LoginPage.tsx`, `lib/api.ts`) y manejo de
certificado autofirmado en Electron (`electron/main.cjs`).

## Gaps conocidos, no resueltos en esta sesión

- **Retención** (mitad de TODO-04): sin política de cuánto tiempo se guardan transcripts ni
  mecanismo de purga.
- **NFR-07** (cumplimiento regulatorio de grabación): sigue sin confirmar — motivo por el que
  "replay" se acotó a transcripción, no audio.
- **Framework de test de frontend**: no existe ninguno en el repo. `LoginPage.tsx`,
  `ScenarioEditorPage.tsx`, y los cambios de `PerformancePage.tsx`/`CallPage.tsx` se verificaron
  con `tsc --noEmit` + `npm run build` en verde y revisión manual de código, no con tests
  automatizados de UI. No se introdujo un framework nuevo (vitest/jest) sin que el usuario lo
  pidiera — es un gap a decidir, no una omisión silenciosa.
- **Certificado autofirmado en Electron**: `certificate-error` confía en cualquier cert inválido
  como parche para poder hablarle al backend real — ver el comentario en
  `frontend/electron/main.cjs` sobre el trade-off. El endurecimiento correcto (fijar el
  fingerprint específico) queda pendiente.
- **Heurística de completitud del motor de métricas**: coincidencia de palabra clave, no
  extracción semántica real — documentado en `core/scoring.py` como simplificación deliberada,
  candidato a revisar con uso real.
- **VAD automático (ADR-0005)**: sigue sin implementar — decisión explícita del usuario para
  este alcance, no un olvido; `recording.start`/`recording.stop` explícitos.

## Verificación

- `apps/voice-agent`: 89 tests de pytest, todos verdes (incluye stubs de `DispatcherPort`/
  `SpeechToTextPort`/`TextToSpeechPort`/`MicrophonePort` — no se corrió contra Whisper/Kokoro/
  Claude/sounddevice reales en esta sesión).
- `frontend`: `tsc --noEmit` y `npm run build` en verde.
- **Pendiente de correr en esta sesión** (requiere hardware/credenciales reales, no disponibles
  en este entorno): una llamada real de punta a punta con `server_main.py` + `npm run dev`,
  incluyendo el caso de matar el servidor a mitad de llamada para confirmar el flujo
  `network_drop` contra la UI real, no solo contra el test de integración con stubs.
