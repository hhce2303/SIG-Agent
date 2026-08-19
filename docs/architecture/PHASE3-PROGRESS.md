# Estado de Fase 3 — seguimiento técnico

Este documento rastrea el checklist de cierre de
[Fase 3 del roadmap](../designs/roadmap-3-fases.md#fase-3--cierre-del-lazo-de-impacto-real--robustecimiento)
punto por punto, con el mismo formato que [PHASE1-PROGRESS.md](./PHASE1-PROGRESS.md) y
[PHASE2-PROGRESS.md](./PHASE2-PROGRESS.md). No duplica el roadmap ni [TODOS.md](./TODOS.md) —
dice, para cada ítem de Fase 3, si está `DONE`, `IN PROGRESS`, `BLOCKED`, o **deliberadamente no
construido** (con la razón), con la evidencia que lo respalda.

**Última actualización:** 2026-08-19 (sesión 6, primera sesión de Fase 3).

## Decisiones tomadas con el usuario antes de construir (mismo patrón que Fase 2)

Fase 3 tiene varios ítems condicionados explícitamente por el roadmap ("solo si...", "si no se
resolvió ya..."). Antes de escribir código se confirmaron 3 decisiones para no construir sobre
una condición sin cumplir ni inventar una decisión de negocio:

1. **Barge-in/full-duplex, híbrido local+LAN (Approach C), revisión multi-sede**: el usuario
   confirmó dejarlos como contingencia no cumplida — mismo tratamiento que TODO-12 (streaming)
   en Fase 2. TODO-08 (spike de Gate 0) sigue `PENDING` sin evidencia de haberse corrido, así
   que no hay base para construir barge-in; no hay caso real de WFH para el híbrido; no hay
   evidencia de expansión a más de una ubicación.
2. **SSO corporativo**: el usuario confirmó saltarlo en esta sesión. TODO-02 sigue exactamente
   como estaba — sin proveedor decidido, sin dueño, ADR-0008 no lo asumió.
3. **Fuente de datos de incidentes reales**: el usuario confirmó captura manual dentro de la
   app — no existe ningún sistema de post-mortems/incidentes con el que integrar.

## Métrica de resultado real

| Ítem del roadmap | Estado | Evidencia |
|---|---|---|
| Captura de incidentes reales | **DONE** | `core/ports.py::IncidentOutcome`/`IncidentOutcomePort`, `persistence/sqlite_incident_store.py::SQLiteIncidentStore`. CRUD por REST (`GET/POST/DELETE /incidents`) en `server/app.py`. `test_incidents.py` (6 tests). |
| "Entrenado vs. no entrenado" | **DONE, derivado, no capturado a mano** | `core/impact_metrics.py::_was_trained_before` — un supervisor cuenta como entrenado respecto a un incidente si tiene al menos una `SessionRecord` con `outcome == "ended"` (puntuada, no interrumpida por red) y `ended_at` anterior a la fecha del incidente. Se decidió así (en vez de un campo manual "¿estaba entrenado?") para no depender de que alguien lo recuerde o reporte bien — el sistema ya tiene esa respuesta en `PersistencePort`. |
| Correlación agregada | **DONE** | `core/impact_metrics.py::compute_impact_report` — promedios y tasas por grupo (rating promedio, % datos críticos capturados, % protocolo seguido), con un umbral mínimo de muestra (`MIN_SAMPLE_SIZE_FOR_CONFIDENCE = 5` por grupo) antes de marcar el reporte como concluyente — documentado como heurística de calibración, mismo espíritu que las bandas de `core/scoring.py`. Expuesto por `GET /impact-report`. `test_impact_metrics.py` (7 tests, dominio puro sin SQLite/FastAPI). |
| Exposición respeta la visibilidad self-only (TODO-04) | **DONE, por diseño** | El reporte de impacto solo expone conteos/promedios agregados por grupo — nunca un cruce supervisor específico + resultado individual. La lista de incidentes individuales (`GET /incidents`) sí es visible a cualquier sesión autenticada — ver TODO-16 (no hay RBAC) sobre esa brecha conocida. |
| UI | **DONE** | `frontend/src/pages/ImpactPage.tsx` — formulario de registro + tabla de incidentes + comparación entrenado/no entrenado. Nueva entrada de navegación "Impact" en `Sidebar.tsx`, ruta `/impact` en `App.tsx`. |

## Lazo de retroalimentación

| Ítem del roadmap | Estado | Evidencia |
|---|---|---|
| Post-mortem → escenario | **DONE** | `POST /incidents/{id}/promote-to-scenario` (`server/app.py`) crea un `Scenario` borrador (`briefing` = notas del post-mortem, `critical_data_points` vacío a propósito) y marca `IncidentOutcome.promoted_scenario_id` para no duplicar. Reusa el editor CRUD ya existente de Fase 2 en vez de un segundo formulario — el frontend navega directo a `/scenarios/{id}/edit` tras promover. `test_server_app.py::test_promote_incident_creates_a_draft_scenario_from_the_post_mortem` (incluye el caso de promover dos veces → 409). |

## Robustecimiento — ítems explícitamente NO construidos en esta sesión

| Ítem del roadmap | Estado | Razón |
|---|---|---|
| Barge-in / full-duplex | **NO construido — deliberadamente** | Condicionado por el roadmap a evidencia de Fase 0-2 que TODO-08 sigue marcando `PENDING` sin correr. Confirmado por el usuario, ver arriba. Mismo tratamiento que TODO-12. |
| Híbrido local + fallback LAN (Approach C, ADR-0004) | **NO construido — deliberadamente** | Condicionado a un caso real de entrenamiento remoto/WFH que no existe. Ver TODO-15 (nuevo). |
| Revisión de ADR-0004/ADR-0001 por multi-sede | **NO construido — deliberadamente** | Sin evidencia de expansión a más de una ubicación. TODO-13/TODO-14 sin cambios de estado. |
| SSO corporativo | **NO construido — deliberadamente** | TODO-02 sigue `IN PROGRESS` exactamente como estaba — sin proveedor decidido, sin dueño. |

## Auto-update del cliente Electron

| Ítem | Estado | Evidencia |
|---|---|---|
| Mecanismo de auto-update | **DONE** | `electron-updater` (nueva dependencia, `frontend/package.json`) cableado en `frontend/electron/main.cjs::initAutoUpdate` — `checkForUpdatesAndNotify()` al arrancar empaquetado (`app.isPackaged`, nunca en `npm run dev`) + chequeo periódico cada 4h. Usa la notificación nativa del SO al terminar de descargar (se aplica al reiniciar), sin un diálogo custom nuevo. |
| Feed de actualizaciones | **DONE, GitHub Releases** | `build.publish` en `package.json` apunta al repo real (`hhce2303/SIG-Agent`, público — `electron-updater` lee releases públicos sin token). Nuevo script `npm run release:win` (requiere `GH_TOKEN` con permiso de subir assets, solo en la máquina que empaqueta el release, nunca en el cliente de un supervisor). |
| **Falta / riesgo conocido** | — | No verificado contra un release real todavía (requiere cortar un tag + `GH_TOKEN`, no disponible en este entorno). El instalador NSIS no está firmado (sin certificado de code-signing) — Windows SmartScreen puede advertir en la instalación inicial; esto no bloquea el mecanismo de auto-update en sí, es una fricción de primera instalación aparte. |

## Brecha nueva descubierta en esta sesión

- **TODO-16 (nuevo): no existe RBAC.** El registro/reporte de incidentes está pensado para un
  manager/RRHH, pero cualquier sesión autenticada puede usarlo hoy — misma brecha implícita que
  ya tenía el CRUD de escenarios, ahora más visible. No se inventó un sistema de roles sin que
  el usuario lo pidiera. Ver detalle en [TODOS.md](./TODOS.md#todo-16).

## Verificación

- `apps/voice-agent`: **106 tests de pytest, todos verdes** (89 previos de Fase 1/2 + 17 nuevos:
  6 de `SQLiteIncidentStore`, 7 de `core/impact_metrics.py`, 4 de integración de servidor).
- `frontend`: `tsc --noEmit` y `npm run build` en verde.
- **Pendiente de correr en esta sesión** (requiere infraestructura real, no disponible en este
  entorno): un release real publicado en GitHub para confirmar que un cliente empaquetado
  detecta, descarga, y aplica la actualización de punta a punta.
