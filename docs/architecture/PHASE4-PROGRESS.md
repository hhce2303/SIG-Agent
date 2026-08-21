# Estado de la propuesta de escenarios de video — seguimiento técnico

Rastrea la implementación de [escenarios-de-video.md](../designs/escenarios-de-video.md)
(generado por `/autoplan` el 2026-08-21, implementado por `/loop` la misma sesión), con el mismo
formato que [PHASE1-PROGRESS.md](./PHASE1-PROGRESS.md)/[PHASE2-PROGRESS.md](./PHASE2-PROGRESS.md)/
[PHASE3-PROGRESS.md](./PHASE3-PROGRESS.md). No es una de las 3 fases del
[roadmap original](../designs/roadmap-3-fases.md) — es una extensión de la "lazo de
retroalimentación" de Fase 3, aprobada explícitamente por el usuario en el Final Approval Gate de
`/autoplan`, con alcance propio y su propio doc de diseño.

**Última actualización:** 2026-08-21 (sesión única, autoplan + implementación completa).

## Decisiones tomadas con el usuario antes de construir

1. **Fuente de video (real vs. dramatizado)**: el usuario confirmó en el Final Approval Gate que
   legal/RRHH ya evaluó y aprobó el uso de video real de casos — registrado en
   [TODO-18](./TODOS.md#todo-18) con la misma nota honesta que TODO-05 (palabra del usuario en
   esta sesión, no una revisión legal formal adjunta a este repo).
2. **Fix de TODO-17 y auth de video (TODO-19) como bloqueantes duros, no negociables**: ambos
   confirmados independientemente por las voces de CEO y Eng de `/autoplan` como riesgo de
   producto/seguridad, no preferencia — implementados antes que cualquier otra cosa de esta lista.
3. **/goal (aclaración de producto dada durante `/loop`)**: dos opciones explícitas para el
   entrenando — escenario de texto vs. video — con varios videos distintos en la librería (no
   varios videos por escenario), cada uno con su propio contexto de texto (`briefing`, reusado
   sin cambios) y su propio ground truth anclado a timestamps.

## Arquitectura (ver ADR-0009/ADR-0010/ADR-0011)

| Ítem | Estado | Evidencia |
|---|---|---|
| Fix de TODO-17 (`match_hints`) | **DONE** | `core/ports.py::CriticalDataPoint.match_hints`, `core/scoring.py::_matches_point`. Retrocompatible por diseño (JSON blob, sin `ALTER TABLE`) — `test_scenarios.py::test_match_hints_round_trip_through_the_json_column`. Aplicado también a los 3 escenarios sembrados (`persistence/sqlite_scenario_store.py::_seed_scenarios`). `test_scoring.py` (4 tests nuevos, incluyendo el caso real de TODO-17). |
| Entidad de video (`ScenarioVideo`/`VideoGroundTruthPoint`) | **DONE, tabla nueva** | `core/ports.py`, `persistence/sqlite_scenario_video_store.py::SQLiteScenarioVideoStore` — tabla `scenario_videos` propia, `scenarios` sin tocar (ver [TODO-20](./TODOS.md#todo-20)). `test_scenario_videos.py` (5 tests). |
| Scoring de video (cobertura, sin panel paralelo) | **DONE** | `core/scoring.py::score_session` mezcla `critical_data_points + video_ground_truth` en la misma lista de puntos — `collected`/`missing` ya incluyen cobertura de video sin ninguna clave nueva. `test_scoring.py::test_video_ground_truth_folds_into_the_same_collected_missing_arrays`. |
| Tiempo de reacción (`video_reaction_seconds`) | **DONE** | `core/scoring.py::_video_reaction_seconds`, anclado a `video_ended_at` (evento WS `video.ended`, reloj de servidor), nunca a `started_at`. Nota cualitativa en `strengths`/`improvements`, nunca un número junto al score (hallazgo de diseño). `test_scoring.py` (3 tests, incluyendo el caso de "café de por medio"). |
| Auth de streaming de video | **DONE** | `auth/video_token.py::HmacVideoTokenIssuer` (ADR-0009) + `server/video_streaming.py` (Range requests manuales). Rutas: `GET /scenarios/{id}/video` (bearer, emite token corto), `GET /scenarios/{id}/video/stream` (token de video, no bearer). `test_video_token.py` (6), `test_video_streaming.py` (9), `test_server_video.py` (streaming/auth: 6 tests). |
| Gate de rol mínimo (managers) | **DONE, acotado** | ADR-0011 — `SessionTokenClaims.role`, `MANAGER_PASSPHRASE` (falla cerrado si no se configura), `_require_manager` solo en `promote-to-scenario` cuando el request incluye video. `test_auth.py` (2), `test_server_video.py` (3 tests de rol). |
| Regresión de topología compartida (5 stores, 1 archivo) | **DONE, descubierto durante esta revisión, independiente del video** | `test_shared_sqlite_topology.py`. |

## Editor de escenarios de video + integración con incidentes

| Ítem | Estado | Evidencia |
|---|---|---|
| `has_video` en el CRUD de escenarios existente | **DONE** | `server/app.py::_scenario_out`/`_scenario_summary` (derivado, `Scenario` sin cambios). `frontend/src/types.ts::ScenarioSummary`. |
| Autoría de ground truth de video (editor) | **DONE** | `frontend/src/pages/ScenarioEditorPage.tsx` — sección nueva "Video scenario (optional)", visible solo editando un escenario ya existente (necesita `scenario_id` real). Inputs de `match_hints` (TODO-17) agregados también a `critical_data_points` existente. |
| Adjuntar video real al promover un incidente | **DONE** | `server/app.py::promote_incident_to_scenario` (body opcional `video`, gateado por rol). `frontend/src/pages/ImpactPage.tsx` — botón "Promote with video" visible solo con `role == "manager"` (pista de UI; el servidor re-verifica). `test_server_video.py` (promote: 3 tests). |
| Dos opciones explícitas: texto vs. video | **DONE** | `frontend/src/pages/ScenariosPage.tsx` — toggle de dos pestañas filtrando por `has_video` (pedido explícito del `/goal`). `HomePage.tsx` marca escenarios de video con 🎬 en el selector rápido. |

## Flujo de llamada en vivo con video

| Ítem | Estado | Evidencia |
|---|---|---|
| Gate pre-llamada compartido (un solo lugar decide) | **DONE** | `frontend/src/pages/CallPage.tsx` — ni `HomePage.tsx` ni `ScenariosPage.tsx` mandan `call.start` directo; CallPage decide según `has_video` (hallazgo de diseño #1 — dos entry points, una sola lógica de gate). |
| Reproductor + interstitial de calma, sin auto-avance | **DONE** | `frontend/src/components/PreCallVideoGate.tsx` — `controls` nativo (rebobinar permitido), sin auto-avance de "video terminó" a "llamada empezó", botón "Skip video, start call" enmarcado como salida técnica. |
| Estado vacío (sin video) invisible | **DONE** | Mismo componente `CallPage.tsx` — si `getScenarioVideoAccess` devuelve `null` (404), sigue directo a `startCall()` sin ningún paso intermedio. |
| Evento `video.ended` (reloj de servidor) | **DONE** | `frontend/src/types.ts::EngineCommand`, `server/app.py` (`elif command == "video.ended"`), con protección contra staleness entre escenarios distintos en la misma conexión WS (`video_ended_scenario_id`). |
| Cobertura/omisiones de video en el debrief | **DONE, cero UI nueva** | `SessionBreakdown.tsx` no necesitó ningún cambio — `collected`/`missing` ya incluyen los puntos de video por diseño del backend (ver tabla de arquitectura arriba). |

## Deliberadamente no construido en esta sesión

- **Upload de video por UI.** v1 usa una ruta de archivo colocada manualmente en disco por un
  administrador (`video_path` en el editor) — recorte de alcance explícito del plan aprobado, no
  un olvido. Ver "Scope Decision" en escenarios-de-video.md.
- **Extracción automática de ground truth por IA de visión.** Approach B del plan, rechazada por
  falta de evidencia de demanda y por agregar un modo de falla nuevo — ver ADR-0010.
- **Replay del video durante el debrief.** El hallazgo de diseño lo marcó "si se muestra, opt-in
  y colapsado" — no es un requisito, y no se construyó esta sesión. Candidato a TODOS.md si se
  pide explícitamente.
- **RBAC completo.** ADR-0011 resuelve solo el gate mínimo para video de incidentes — TODO-16
  sigue abierto para el resto (editor de escenarios, CRUD de incidentes en general).
- **Extracción semántica vía LLM para scoring de video.** ADR-0010 la deja como mejora futura
  documentada, contingente a evidencia real de que `match_hints` no alcanza.

## Cobertura de tests

156 → 158 tests en `apps/voice-agent/src/` (todos verdes), + `frontend`: `tsc --noEmit` y
`vite build` limpios. Archivos nuevos: `test_scenario_videos.py`, `test_video_token.py`,
`test_video_streaming.py`, `test_server_video.py`, `test_shared_sqlite_topology.py`. Extendidos:
`test_scoring.py`, `test_scenarios.py`, `test_auth.py`.

## ADRs de esta sesión

- [ADR-0009](./adr/0009-auth-de-streaming-de-video.md) — mecanismo de auth para servir video.
- [ADR-0010](./adr/0010-scoring-de-ground-truth-de-video.md) — mecanismo de comparación para
  scoring de video (reusa `match_hints`, no LLM todavía).
- [ADR-0011](./adr/0011-gate-de-rol-minimo-video-de-incidentes.md) — gate de rol mínimo
  (manager) antes de exponer video real de incidentes.

## Nota sobre control de versiones

Todo lo de esta sesión vive en la branch `feature/video-scenarios`, sin commitear todavía — por
política, los commits solo se hacen cuando el usuario lo pide explícitamente. `git status`/`git
diff` en esa branch tienen el detalle completo mientras tanto.
