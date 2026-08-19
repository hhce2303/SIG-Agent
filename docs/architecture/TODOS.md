# TODOS — decisiones pendientes y riesgos conocidos, voice-agent

Estado: `PENDING` (no iniciado) / `IN PROGRESS` / `[RESOLVED vX.X]`. IDs estables, nunca se
reordenan ni se borran — un TODO resuelto queda marcado, no desaparece.

## Bloqueantes de Fase 1

### TODO-01
**Motor de persistencia.** Estado: IN PROGRESS.
No existe hoy ninguna capa de storage (escenarios, métricas, historial son greenfield — ver
[ADR-0006](./adr/0006-arquitectura-hexagonal.md)). Elegir motor (SQLite/Postgres/otro) es un
ADR pendiente de escribir, no un detalle de implementación. **Actualización 2026-08-19:**
[ADR-0007](./adr/0007-motor-de-persistencia.md) (SQLite embebido) — `accepted` por el usuario.
Queda IN PROGRESS (no RESOLVED) hasta que el adaptador esté implementado y en uso por el
servidor real, no solo decidido.

### TODO-02
**Mecanismo de autenticación de supervisores.** Estado: IN PROGRESS.
¿Hay un directorio/SSO corporativo existente para integrar, o se necesita uno propio? Sin
dueño nombrado. Relacionado: [NFR-04](./nfr.md#nfr-04). Bloqueante antes de fusionar código de
servidor según la revisión de ingeniería de `/autoplan`. **Actualización 2026-08-19:**
[ADR-0008](./adr/0008-mecanismo-de-autenticacion-de-sesion.md) (token de sesión propio, sin
asumir SSO corporativo) — `accepted` por el usuario. Sigue IN PROGRESS: falta implementar y
usar el adaptador en el servidor real, y la pregunta de si existe además un SSO corporativo
real sigue sin dueño y sigue abierta (no bloquea este mecanismo, ver ADR-0008).
**Actualización 2026-08-19 (sesión de Fase 3):** roadmap Fase 3 pedía "integración de auth con
SSO corporativo si no se resolvió ya en Fase 1" — no se resolvió, y el usuario confirmó
explícitamente saltar esto en esta sesión (sin proveedor decidido, sin dueño nombrado, no hay
base para elegir entre un adaptador OIDC genérico vs. uno específico sin esa decisión). Sigue
exactamente como estaba: `IN PROGRESS`, sin código nuevo de SSO.

### TODO-03
**Dueño operativo de la caja RTX.** Estado: PENDING.
¿IT o el equipo del sponsor? Sin nombre asignado, este tipo de pieza (servidor + auth en la red
interna) suele estancarse en revisión de seguridad por meses.

### TODO-04
**Política de retención y visibilidad del historial.** Estado: **IN PROGRESS** (mitad resuelta).
¿Cuánto tiempo se retienen audio/transcripts? ¿Quién puede ver el historial de quién — el
propio supervisor, su jefe, RRHH? Ver [NFR-06](./nfr.md#nfr-06). Sin esto, los supervisores no
practican honestamente. **Actualización 2026-08-19 (Fase 2):** la mitad de **visibilidad** se
resolvió — el usuario confirmó self-only (el propio supervisor ve su historial completo, jefe/
RRHH sin acceso directo), implementado en `persistence/sqlite_store.py::list_sessions`
(escopeado siempre por el `supervisor_id` del token verificado, nunca por lo que mande el
cliente) y ejercitado en `test_persistence.py::test_list_sessions_scopes_by_supervisor_...`.
**Sigue pendiente la mitad de retención** — no hay política de cuánto tiempo se guardan
transcripts (no se captura/guarda audio en ningún punto de esta arquitectura), ni un mecanismo
de purga por antigüedad — ADR-0007 ya anticipó que el schema debería soportar esto una vez que
la política exista.

### TODO-05
**Cumplimiento regulatorio de grabación de voz.** Estado: PENDING.
No se confirmó ninguna restricción legal conocida (leyes estatales de consentimiento para
grabar empleados, política de monitoreo de RRHH, residencia de datos) durante el baseline de
arquitectura. Ver [NFR-07](./nfr.md#nfr-07) — se documenta explícitamente como pendiente, no se
asume que "no aplica".

### TODO-06
**Segundo ingeniero/revisor.** Estado: PENDING.
Bus factor de 1 persona en todo el pipeline STT/LLM/TTS, sin tests. Nombrar antes de Fase 1 —
debería empezar por el harness de tests ([NFR-10](./nfr.md#nfr-10)), antes de tocar el rewrite.

### TODO-07
**Presupuesto de capital para la GPU RTX.** Estado: PENDING.
El pedido original solo menciona tiempo asignado por el jefe de área, no capex de hardware.
Confirmar por separado antes de programar el spike de Gate 0.

## Condiciona decisiones ya tomadas

### TODO-08
**Resultado del spike de Gate 0.** Estado: PENDING.
Latencia end-to-end (incluyendo round-trip a Claude), prueba de red real con dos máquinas, y
user-test barato de VAD vs. push-to-talk con 2-3 supervisores. Condiciona directamente
[ADR-0004](./adr/0004-topologia-de-despliegue.md) y [ADR-0005](./adr/0005-audio-en-vivo-vad-sin-barge-in.md).
**Nota (Fase 3):** también condiciona directamente "revisitar barge-in/full-duplex" del
roadmap Fase 3 — sigue sin evidencia de haberse corrido, así que barge-in no se construyó en la
sesión de Fase 3 (el usuario lo confirmó explícitamente). No es un TODO nuevo porque es
exactamente la misma condición que ya bloquea ADR-0005.

### TODO-09
**Clasificación de causa raíz del incidente documentado.** Estado: PENDING.
¿Pánico/habla bajo presión, falta de datos a la mano, no saber a quién llamar, o
desconocimiento de protocolo? Informa qué debe entrenar realmente el simulador — hacerlo antes
de cerrar el alcance de Fase 1.

### TODO-10
**Fórmula de ponderado/score de métricas.** Estado: **[RESOLVED 2026-08-19]**.
Peso relativo de tiempo-hasta-dato-crítico, completitud, claridad/muletillas, y tiempo total.
Resuelto por el usuario: completitud 40% / tiempo-a-dato-crítico 30% / claridad 20% / tiempo
total 10% — implementado en `core/scoring.py::ScoreWeights` (Fase 2), configurable por env vars
(`METRICS_WEIGHT_*`) sin tocar código. La heurística de completitud (coincidencia de palabra
clave contra el transcript) queda documentada en el docstring del módulo como simplificación
mejorable, no como decisión final de producto — candidato a revisar si en uso real resulta
demasiado burda.

### TODO-11
**Formato del editor de escenarios.** Estado: **[RESOLVED 2026-08-19]**.
Campos estructurados guiados vs. texto libre (tipo el `SCENARIO` string actual). Resuelto por el
usuario: campos estructurados (`title`, `category`, `difficulty`, `language`, `description`,
`critical_data_points`) + una narrativa libre (`briefing`) — implementado en
`core/ports.py::Scenario`/`ScenarioPort`, `persistence/sqlite_scenario_store.py` (Fase 2). Los
`critical_data_points` son el puente hacia el motor de métricas (TODO-10) — sin campos
estructurados, "completitud" no se podría calcular de forma mecánica.

## Contingencias (se activan solo si su condición ocurre)

### TODO-12
**Streaming de respuesta de Claude.** Estado: PENDING (contingente a TODO-08).
Si el spike de Gate 0 muestra que el round-trip a Claude por sí solo rompe el presupuesto de
[NFR-01](./nfr.md#nfr-01), tratar la integración de streaming (tokens de Claude → síntesis
incremental de TTS) como workstream propio de Fase 2, no como nota al pie. Ver
[ADR-0003](./adr/0003-proveedor-llm-claude-api.md), sección Risks.

### TODO-13
**Revisitar ADR-0004 si la operación crece a más de una ubicación.** Estado: PENDING
(contingente a expansión de negocio).
La topología de servidor LAN + RTX se decidió asumiendo una sola ubicación. Si se agregan
sitios, replicar servidor + dueño + auth por sitio puede invertir la recomendación hacia el
ejecutable standalone (Approach A de ADR-0004). **Actualización 2026-08-19 (Fase 3):** sigue sin
evidencia de expansión a más de una ubicación — no revisitado en esta sesión, confirmado
explícitamente por el usuario.

### TODO-14
**Revisitar ADR-0001 si se necesita alta concurrencia.** Estado: PENDING (contingente a cambio
de escala).
Python fue elegido asumiendo concurrencia=1 ([NFR-11](./nfr.md#nfr-11)). Si el proyecto
creciera a necesitar servir muchas sesiones simultáneas, esta decisión debería revisitarse.

### TODO-15
**Híbrido local + fallback LAN (Approach C de ADR-0004).** Estado: PENDING (contingente a
entrenamiento remoto/WFH real). Roadmap Fase 3: descartada por ahora, revisitar solo si
entrenamiento remoto/WFH se vuelve un caso real — no por defecto. **Actualización 2026-08-19:**
el usuario confirmó explícitamente no construir esto en la sesión de Fase 3 (no hay evidencia
de un caso real de WFH) — no construido a propósito, mismo tratamiento que TODO-12.

### TODO-16
**No existe control de acceso por rol (RBAC) en este repo.** Estado: PENDING.
Toda sesión autenticada tiene el mismo privilegio — no hay distinción entre supervisor/manager/
RRHH. Esto ya era una brecha implícita en el CRUD de escenarios (Fase 2), pero se vuelve más
visible en Fase 3: el registro manual de incidentes reales y el reporte de impacto agregado
(`GET /impact-report`, `POST /incidents`) están pensados conceptualmente para un manager/RRHH,
pero hoy cualquier supervisor autenticado puede leerlos y escribirlos, igual que ya pasa con el
editor de escenarios. El reporte de impacto en sí solo expone estadísticas agregadas por grupo
(nunca supervisor + resultado individual, ver `core/impact_metrics.py`), así que no reabre
TODO-04 (visibilidad self-only del historial de sesiones) — pero el registro de incidentes
individual (`GET /incidents`) sí es visible para cualquier sesión autenticada. Si el registro
manual de incidentes necesita quedar restringido a un rol de manager/RRHH real, eso requiere
diseñar RBAC primero (quién es "manager"? ¿mismo token, claim nuevo, SSO con roles?) — no se
inventó unilateralmente en esta sesión.
