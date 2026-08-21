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
**Dueño operativo de la caja RTX.** Estado: **[RESOLVED 2026-08-20]**.
¿IT o el equipo del sponsor? Sin nombre asignado, este tipo de pieza (servidor + auth en la red
interna) suele estancarse en revisión de seguridad por meses. **Actualización 2026-08-20
(sesión de Gate 0/pruebas reales):** el usuario confirmó que el Departamento de IT es el dueño
operativo de la caja (parches, uptime, revisión de seguridad) — resuelve la pregunta abierta de
"¿IT o el equipo del sponsor?". Queda a nivel de departamento, no una persona nombrada
específica — si se necesita un punto de contacto individual, es un TODO nuevo, no algo que este
TODO ya cubra. No resuelve TODO-06 (segundo ingeniero/revisor de código) ni TODO-07 (presupuesto
de capital), que son preguntas distintas sobre la misma pieza.

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

**Actualización 2026-08-20 (sesión de Gate 0/pruebas reales):** la mitad de **retención** ahora
tiene decisión, en dos tramos — la política sigue **IN PROGRESS**, no `RESOLVED`, porque la
decisión existe pero el mecanismo de purga automática todavía no está implementado en código:
- **Durante pruebas** (Gate 0, corrida de punta a punta, y cualquier sesión de prueba interna
  antes de un despliegue real): retención nula — no hay purga, los transcripts de prueba se
  conservan sin límite de tiempo mientras dure esta etapa.
- **En producción (fase beta y sesiones de "tester")**: retención de **1 hora** — un transcript
  de práctica se purga 1 hora después de creado. Esto cumple el requisito de NFR-06 ("debe estar
  resuelta y comunicada antes de almacenar audio/transcripts reales de práctica") para poder
  avanzar a pruebas reales sin violar ese gate — la política ya existe, aunque el purgado de 1h
  en producción es trabajo de implementación pendiente (no bloquea Gate 0 ni la corrida de punta
  a punta de esta sesión, sí bloquea declarar Fase 1 cerrada en sentido estricto contra un
  despliegue real/beta).

### TODO-05
**Cumplimiento regulatorio de grabación de voz.** Estado: **[RESOLVED 2026-08-20]**.
No se confirmó ninguna restricción legal conocida (leyes estatales de consentimiento para
grabar empleados, política de monitoreo de RRHH, residencia de datos) durante el baseline de
arquitectura. Ver [NFR-07](./nfr.md#nfr-07) — se documenta explícitamente como pendiente, no se
asume que "no aplica". **Actualización 2026-08-20 (sesión de Gate 0/pruebas reales):** el
usuario confirmó la vía de resolución: esta es una herramienta interna tipo "trainer/tool", así
que se rige por las condiciones y calidad que ya exige el contrato de la empresa — el uso de
datos sensibles de la empresa (incluida esta herramienta) queda cubierto por el consentimiento
que el empleado ya otorga al firmar su contrato, sin un mecanismo de opt-in nuevo por sesión.
Contexto que reduce el riesgo real de esta decisión: la arquitectura nunca captura ni persiste
**audio** (ver [PHASE2-PROGRESS.md](./PHASE2-PROGRESS.md#gaps-conocidos-no-resueltos-en-esta-sesión)) —
solo transcript de texto, y ahora con retención acotada (ver TODO-04 arriba). **Nota honesta:**
esta es una decisión de negocio del usuario, no una revisión legal formal (no hubo validación de
un abogado/RRHH sobre el texto real del contrato ni sobre leyes estatales específicas de
consentimiento para grabar) — se documenta como la resolución adoptada, no como asesoría legal
verificada.

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
**Resultado del spike de Gate 0.** Estado: **IN PROGRESS** (spike de latencia corrido con
resultado real; falta la prueba de red con dos máquinas y el user-test con supervisores reales).
Latencia end-to-end (incluyendo round-trip a Claude), prueba de red real con dos máquinas, y
user-test barato de VAD vs. push-to-talk con 2-3 supervisores. Condiciona directamente
[ADR-0004](./adr/0004-topologia-de-despliegue.md) y [ADR-0005](./adr/0005-audio-en-vivo-vad-sin-barge-in.md).
**Nota (Fase 3):** también condiciona directamente "revisitar barge-in/full-duplex" del
roadmap Fase 3 — sigue sin evidencia de haberse corrido, así que barge-in no se construyó en la
sesión de Fase 3 (el usuario lo confirmó explícitamente). No es un TODO nuevo porque es
exactamente la misma condición que ya bloquea ADR-0005.

**Actualización 2026-08-20 (arranque de Gate 0):** el usuario confirmó explícitamente empezar
a correr Gate 0 en esta sesión, seguido de una corrida de punta a punta contra hardware real.
Secuencia confirmada para VAD (ADR-0005): no se implementa/activa VAD automático hasta pasar
primero las pruebas con push-to-talk explícito (`recording.start`/`recording.stop`) y confirmar
la conexión completa con el scope de la UI (indicador de turno, estados de conexión) — mismo
espíritu que ADR-0005 ya preveía ("revisitar solo si la evidencia... lo muestra"), ahora con un
criterio de secuencia explícito en vez de solo una condición abierta. No cambia la Decision de
ADR-0005 ni de TODO-08 — es un orden de ejecución, no una decisión de arquitectura nueva.

**Resultado del spike de latencia (2026-08-20):** corrido en esta máquina (RTX 3050 6GB +
i9-10900X, confirmada por el usuario como la caja RTX candidata), pipeline real STT (Whisper
`small`, `cpu`/`int8` — la config exacta de `server_main.py`) → Claude API real → TTS (Kokoro,
tiempo hasta el primer chunk de audio listo), 5 trials, entrada de audio sintética (una línea de
supervisor generada por TTS, no voz humana en vivo — ver metodología abajo):

| Etapa | media | mediana | min | max |
|---|---|---|---|---|
| STT (Whisper, cpu/int8) | 2346ms | 2253ms | 2230ms | 2711ms |
| Claude API (real) | 1072ms | 955ms | 839ms | 1360ms |
| TTS Kokoro (a 1er chunk) | 2204ms | 2428ms | 1111ms | 3155ms |
| **TOTAL end-to-end** | **5622ms** | **5852ms** | **4257ms** | **7223ms** |

**NO cumple NFR-01** (objetivo <1500ms, ideal <800ms) — la media mide **~3.75x el objetivo**, en
cualquier trial individual, incluido el mejor caso (4257ms).

**Hallazgo adicional, no solo el número:** `torch.cuda.is_available()` es `False` en este
entorno — Whisper y Kokoro corrieron 100% en CPU pese a que la RTX 3050 existe físicamente
(`nvidia-smi` la reporta) — falta el runtime de CUDA (`cublas64_12.dll` no encontrado; probado
`WhisperSTT(device="cuda")` y falló con ese error exacto). Esto **no es lo mismo** que "la GPU
no alcanza" — es que el stack de PyTorch/ctranslate2 instalado en este entorno no tiene el
runtime de CUDA funcional todavía para usarla. No se intentó reparar el toolchain de CUDA en
esta sesión (instalar el runtime correcto es una tarea de infraestructura aparte, potencialmente
de varios GB de descarga) — queda como palanca sin probar, no como palanca descartada.

**Metodología / lo que este resultado NO cubre todavía:**
- Corrido en una sola máquina — falta el spike de red real con un segundo cliente Electron
  sobre la LAN real (jitter, cortes), que requiere una segunda máquina física.
- Entrada de audio sintética (dictada por TTS), no una voz humana real grabada en vivo — razonable
  como proxy de la velocidad de inferencia del modelo, no de condiciones acústicas reales.
- El user-test barato de 2-3 supervisores reales (push-to-talk vs. VAD) sigue sin hacerse —
  requiere personas reales, no algo que se pueda ejecutar sin ellas.
- TODO-09 (causa raíz) se resolvió esta misma sesión — ver abajo.

**Implicación para ADR-0004/ADR-0005:** el spike no confirma que la topología LAN+RTX (ADR-0004)
sea insuficiente — confirma que, tal como está configurado y con el toolchain de CUDA roto en
esta instancia, ni siquiera la caja candidata cumple NFR-01 hoy. La palanca más obvia (activar
GPU real para Whisper/Kokoro) no se probó todavía porque el entorno no lo permite en su estado
actual — hasta que se repare eso, cualquier decisión sobre ADR-0004 basada en este número sería
prematura. Streaming de respuesta de Claude (TODO-12) sigue siendo la mitigación de reserva si
GPU no cierra la brecha.

### TODO-09
**Clasificación de causa raíz del incidente documentado.** Estado: **[RESOLVED 2026-08-20]**.
¿Pánico/habla bajo presión, falta de datos a la mano, no saber a quién llamar, o
desconocimiento de protocolo? Informa qué debe entrenar realmente el simulador — hacerlo antes
de cerrar el alcance de Fase 1. **Actualización 2026-08-20 (sesión de Gate 0/pruebas reales):**
el usuario confirmó **falta de datos a la mano** como causa raíz — el supervisor no tenía la
información crítica (placa, descripción del vehículo, ubicación, etc.) accesible en el momento
de la llamada real, no un problema de pánico ni de desconocimiento de protocolo. Esto valida
retroactivamente que el simulador ya está entrenando lo correcto: `core/scoring.py::ScoreWeights`
pondera **completitud al 40%** (el peso más alto de las 4 categorías, ver
[TODO-10](#todo-10)) y `Scenario.critical_data_points` (ADR de Fase 2) existe específicamente
para que el dispatcher exija esos datos durante la llamada — la arquitectura ya apuntaba a la
causa raíz real antes de que se confirmara explícitamente, no hay que rediseñar el motor de
métricas ni el formato de escenario a partir de este resultado.

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

**Actualización 2026-08-21 (`/autoplan` sobre escenarios de video,
[escenarios-de-video.md](../designs/escenarios-de-video.md)):** dos voces de revisión
independientes (CEO y Eng) escalaron esta brecha de severidad — no por el registro de texto de
incidentes (tolerable como está), sino porque la propuesta de escenarios de video adjuntaría
**video crudo de robos reales** a la misma superficie sin restricción de rol. Si esa propuesta
avanza con video real, un gate de rol mínimo (no el RBAC completo) pasa de "pendiente" a
bloqueante — ver esa nota de diseño, sección Eng, hallazgo 4.2.

## Descubierto en la primera corrida de punta a punta contra hardware real (2026-08-20)

### TODO-17
**La heurística de completitud (`core/scoring.py::_matches_point`) no reconoce datos reales
cuando el supervisor no repite el texto literal del `label` del critical data point.** Estado:
PENDING.

Ya estaba documentado como "simplificación mejorable" en el docstring del módulo — esta sesión
lo confirma con evidencia real, no una sospecha. `_matches_point` compara el `label` de cada
`CriticalDataPoint` (ej. `"What happened"`, `"Vehicle description"`, `"Last known location"`,
`"Approximate time"`) contra el texto del operador — pero esos labels son **preguntas/etiquetas
de UI, no palabras clave de contenido**, así que una respuesta correcta casi nunca los contiene
literalmente.

**Evidencia real** (primera llamada de punta a punta con voz real, Whisper+Claude+Kokoro reales,
sin stubs — escenario Vehicle Theft):
- Transcript real: *"There is a white 2021 Toyota Camry stolen from a shopping center parking
  lot about two hours ago. License plate Alpha Bravo Charlie 123."* + *"It was the Westfield
  Shopping Center."*
- Esto describe correctamente: qué pasó (robo), descripción del vehículo (Toyota Camry blanco
  2021), ubicación (shopping center / Westfield), tiempo aproximado (hace dos horas), y la placa.
- Resultado real del motor de scoring: **Completeness 17/100** — solo `"License plate"` se
  marcó como recolectado. `"What happened"`, `"Vehicle description"`, `"Last known location"`,
  `"Approximate time"` se marcaron como **`missing` pese a haber sido dichos correctamente**,
  porque el operador nunca dijo las palabras literales "vehicle", "description", "location",
  "approximate" o "what"/"happened". `"License plate"` fue el único match, y solo porque el
  guion de prueba usó por coincidencia la misma frase que el label del escenario.
- Esto también arrastra **Time To Critical Data a 4/100** (`_time_to_critical_data` usa el mismo
  `_matches_point`, así que hereda el mismo falso negativo).

**Por qué importa para producción real:** con esta heurística, un supervisor que reporte
correctamente y con lenguaje natural puede recibir un score bajo no por desempeño real sino por
no repetir el vocabulario exacto de la etiqueta del dato — exactamente el resultado no confiable
que TODO-09 (causa raíz: falta de datos a la mano) pide que el simulador entrene bien. El motor
de scoring hoy mide "¿dijiste estas palabras clave?", no "¿comunicaste este dato?".

**No se decidió ni construyó una solución en esta sesión** — el propio docstring de
`core/scoring.py` ya nombra la mejora natural (extracción vía LLM en vez de keyword matching),
pero eso tiene su propio costo/latencia (una llamada más a Claude por turno o al final de la
llamada) que amerita su propio análisis antes de construirse, no una expansión de keywords
manual como parche rápido. Ver también [TODO-10](#todo-10) (fórmula de pesos, no afectada por
esto) y `core/scoring.py` (docstring del módulo, ya lo advertía).

**Actualización 2026-08-21 (`/autoplan` sobre escenarios de video,
[escenarios-de-video.md](../designs/escenarios-de-video.md)):** este TODO deja de ser solo una
mejora de calidad diferible. Dos voces de revisión independientes (CEO y Eng, corriendo ciegas
una de la otra) coincidieron en que construir scoring de "ground truth" de video (cobertura de lo
visible) sobre este mismo mecanismo de keyword-matching literal reproduciría — y probablemente
amplificaría — esta falla exacta, a mayor costo emocional para el entrenando. **Se marca como
bloqueante duro para cualquier extensión de scoring basada en ground truth (video u otro),
no como algo que se pueda diferir junto con esa feature.** No cambia el alcance de este TODO para
los escenarios de texto existentes — sigue PENDING igual que antes, ahora con una razón adicional
para no seguir postergándolo.

## Descubierto en la revisión de la propuesta de escenarios de video (2026-08-21, `/autoplan`)

Ver [escenarios-de-video.md](../designs/escenarios-de-video.md) para el análisis completo
(premisas, alternativas, revisión de diseño e ingeniería). Los tres TODOs siguientes son hallazgos
nuevos de esa revisión, no duplicados de TODOs existentes.

### TODO-18
**Base legal/de consentimiento para contenido de video de terceros en escenarios.** Estado:
**IN PROGRESS** (resuelto a nivel de decisión de negocio; sin implementación de sus
consecuencias todavía — RBAC mínimo de TODO-16/TODO-19).

**Actualización 2026-08-21 (Final Approval Gate de `/autoplan`):** el usuario confirmó que
legal/RRHH ya evaluó y aprobó específicamente el uso de video real de casos de robo para esta
herramienta (no solo el consentimiento general de TODO-05, que no cubría esto). **Nota honesta,
igual que TODO-05:** esta confirmación se registra tal como el usuario la dio en esta sesión —
no hay una revisión legal formal adjunta a este repo ni un documento de sign-off enlazado. Si
en algún momento se necesita auditar esta decisión, el punto de partida es preguntarle al usuario
por el registro/aprobación real de legal/RRHH, no asumir que este TODO por sí solo es esa
evidencia.

Con la base legal resuelta, la condición que queda antes de exponer video real de incidentes es
puramente de ingeniería, ya trackeada por separado: el gate de rol mínimo de TODO-16 (RBAC) y el
mecanismo de auth de servir video de TODO-19 — ambos siguen PENDING y son bloqueantes de
implementación, no de decisión de negocio.

TODO-05 (resuelto) apoya el consentimiento actual en dos patas: (a) es el dato *propio* del
entrenando, y (b) la arquitectura nunca captura ni persiste audio/video real de nadie — solo
transcript de texto. Video real de robos rompe ambas patas: las personas en el video (víctimas,
transeúntes, otros empleados, placas/rostros visibles) nunca dieron consentimiento y no obtienen
nada de él. Sin dueño legal/RRHH nombrado para esta decisión específica (distinta de TODO-05,
que no la cubre). Preguntas concretas a resolver antes de usar metraje real: ¿hay derechos claros
de uso del metraje (de qué sistema de vigilancia viene, de quién)? ¿se requiere redacción de
rostros/placas? ¿aplica alguna ley estatal de biometría (ej. BIPA)? ¿los escenarios de video para
v1 deben ser solo dramatizados/con licencia mientras esto se resuelve? Ver Final Approval Gate de
la nota de diseño para la decisión de negocio inmediata.

### TODO-19
**Mecanismo de auth para servir archivos de video al cliente.** Estado: PENDING (bloqueante de
implementación, no de decisión de negocio).

Todo endpoint REST de este repo requiere un bearer token HMAC (`_bearer_claims`,
`server/app.py:159-166`), pero un tag `<video>` HTML no puede adjuntar un header `Authorization`
a su request. La implementación obvia (montar `StaticFiles`, o pasar un path/URL crudo al
frontend) evita ese boundary de auth por completo. Decisión pendiente entre: (a) tokens firmados
de corta duración por-request en una ruta de streaming dedicada, o (b) fetch-as-blob desde el
frontend con el header bearer + `URL.createObjectURL`. Debe decidirse (y no re-copiarse el patrón
de `?token=` en query param que ya usa el WebSocket, `server/app.py:320`) antes de construir la
ruta de servir video, no descubrirse en producción.

### TODO-20
**Seguridad de migraciones de esquema SQLite — riesgo repo-wide, no solo de esta feature.**
Estado: PENDING.

Los cuatro stores existentes (`sqlite_scenario_store.py`, `sqlite_incident_store.py`,
`sqlite_store.py`, `sqlite_settings_store.py`) usan únicamente `CREATE TABLE IF NOT EXISTS`,
justificado explícitamente en el código como seguro porque "no hay datos reales que migrar"
todavía. Esa justificación está caducando: Gate 0 ya generó datos reales en `sessions.db`
(TODO-04/TODO-08). `CREATE TABLE IF NOT EXISTS` es un no-op contra una tabla que ya existe — agregar
una columna a una tabla existente (ej. `scenarios`) rompe en producción (`sqlite3.OperationalError`)
sin que ningún test lo detecte, porque cada test usa un `tmp_path` nuevo. Este TODO no bloquea
nada hoy (ningún cambio de esquema está en vuelo todavía), pero es la razón por la que la propuesta
de escenarios de video decidió usar solo tablas nuevas (`scenario_videos`, ground truth de video)
y nunca alterar `scenarios` — ver escenarios-de-video.md, hallazgo Eng 1.2. Si algún cambio futuro
sí requiere `ALTER TABLE` sobre una tabla existente, ese es el momento de agregar un
`schema_version` + runner de migración idempotente, no de repetir el patrón actual y confiar en
que nadie lo note.
