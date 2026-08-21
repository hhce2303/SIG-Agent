# Design + Review: Escenarios de entrenamiento basados en video (contexto real de robos)

Generado por `/autoplan` el 2026-08-21 (sin `/office-hours` previo — ver nota de proceso abajo).
Branch: master | Repo: SIG-AGENT | Modo: SELECTIVE EXPANSION
Estado: **APPROVED** (2026-08-21) — premisa de fuente de video resuelta por el usuario en el
Final Approval Gate; plan aprobado tal como está. Implementación queda condicionada a los
prerrequisitos de secuencia ya escritos (TODO-16/17/19/20), no a más decisiones de negocio
pendientes.

**Nota de proceso:** no se encontró design doc previo para esta feature específica (sí existe
uno para el producto completo, [police-call-training-simulator.md](./police-call-training-simulator.md),
ya incorporado como contexto). Se auto-decidió saltar `/office-hours` (principio #6, bias toward
action — el pedido del usuario ya trae problema, evidencia y alcance propuesto concretos) y
sintetizar el "rough plan" directamente a partir del pedido + una investigación real del código y
docs existentes, antes de correr las fases de revisión. Codex no está instalado en esta máquina
(`command -v codex` → not found) — las 3 fases de revisión corrieron en voz única: **Claude
subagent, independiente y ciego a las fases previas** (tag `[subagent-only]` en las 3 tablas de
consenso).

## Pedido original del usuario

> "Nosotros manejamos videos de muchos de los casos de robos que tenemos, o sea que se podría
> cargar un escenario y contexto para el agente y sobre eso obtener otras métricas, y el usuario
> en entrenamiento debe ver el video del robo y comunicar lo máximo posible al agente de policía."

Es decir: cargar un escenario con video real (de casos que la empresa ya tiene) + contexto
asociado; el entrenando ve el video y llama al dispatcher IA reportando lo que vio; el sistema
evalúa qué tan completo/preciso fue ese reporte contra el contenido real del video, y esas
métricas se integran al dashboard existente.

## Problem Statement

El roadmap del producto ya nombra este objetivo explícitamente, sin haberlo construido todavía:
el design doc de origen dice, en Success Criteria, que sin un mecanismo donde "los post-mortems
de incidentes reales retroalimenten la librería de escenarios," la herramienta puede tener 100%
de uso y 0% de impacto real
([police-call-training-simulator.md:190-192](./police-call-training-simulator.md#success-criteria)).
El feature de "real-world incident logging" (commit `5a8058f`, más reciente en el repo) ya
empezó a cerrar ese lazo con texto (notas de incidente → escenario promovido). Este pedido lo
extiende con el activo real que la empresa ya tiene: video de casos reales.

## 0A — Premise Challenge

Corrido por un subagente CEO independiente (ciego al resto de esta revisión), leyendo el código
real (`core/scoring.py`, `core/ports.py`, `core/impact_metrics.py`, `sqlite_incident_store.py`,
la ruta `promote-to-scenario`, y TODOS/NFR/roadmap completos). Hallazgos, en su propia
severidad:

1. **[HIGH] La única evidencia real en este repo apunta contra la premisa de que el estímulo
   (texto vs. video) es el cuello de botella.** TODO-17 documenta una llamada real donde el
   entrenando, trabajando desde el briefing de **texto actual**, dio lo que el propio doc llama
   un "reporte perfecto, completo, en lenguaje natural" — y sacó 17/100 de completitud porque
   `_matches_point` compara por palabra clave literal contra el `label` de la UI, no por
   significado. La falla está 100% en el evaluador, 0% en el estímulo. Nada en este repo sugiere
   que el briefing de texto falle en producir buenos reportes verbales.
   **Sí existe** un argumento legítimo y distinto para el video (entrenar "percibir bajo presión
   y luego reportar" en vez de "recordar un briefing dado"), pero nunca se hizo explícito ni se
   puso a prueba — se presenta como si arreglara el mismo problema que el bug de scoring, cuando
   la falla medida está en otro lado.
2. **Premisas no dichas:** "estímulo más rico ⇒ mejor entrenamiento" (no probado, y el único dato
   real lo contradice); "el ground truth de un video es evaluable igual que los
   `critical_data_points` actuales" (falso — hoy son ~4-6 labels cortos autor-por-humano; un
   ground truth de video que cubra sospechosos/ropa/arma/vehículo/dirección de huida/tiempos
   necesita una autoría estructurada nueva, con su propio costo); "tenemos el video en mano" (el
   usuario lo confirma como activo real — bien, pero derechos de uso/cadena de custodia no están
   verificados en ningún doc); "el consentimiento de contrato de empleado ya cubre esto" — ver
   punto 5, la premisa más consecuente y la que más se contradice a sí misma.
3. **Escenario de arrepentimiento a 6 meses:** (a) el motor de scoring se vuelve *menos*
   confiable, no más — ground truth de video tiene más hechos que comparar que los 4-6
   `critical_data_points` de hoy, así que la misma falla de keyword-matching literal (TODO-17)
   tiene más superficie para dispararse, probablemente penalizando a los entrenandos que mejor
   se desempeñan, justo en el momento (feedback post-incidente) donde `GOALS.md` dice que la
   confianza en el espacio de práctica importa más. (b) Legal/RRHH descubre, después del hecho,
   que hay video de un robo real con un rostro/placa identificable de un tercero (víctima,
   transeúnte, otro empleado) sirviéndose sin control de acceso por rol (`TODO-16`: no existe
   RBAC en este repo — cualquier sesión autenticada puede pegarle a los mismos endpoints).
4. **Alternativas descartadas sin evaluarse:** arreglar `core/scoring.py` primero (beneficia a
   *todo* escenario, texto o video, y es prerrequisito para que el scoring de video no sea
   activamente dañino); poblar `critical_data_points` en escenarios ya promovidos (hoy queda
   vacío a propósito, `PHASE3-PROGRESS.md:42` — la mitad más barata y de menor riesgo del mismo
   lazo de retroalimentación que el roadmap ya pide); un estímulo **solo-audio** vía el pipeline
   TTS/STT que ya existe (aísla "percibir-y-reportar" de "leer-y-reportar" sin ninguna categoría
   nueva de consentimiento ni infraestructura de media); tratar "real vs. dramatizado" como
   intercambiable cuando en realidad son categorías de riesgo legal completamente distintas.
5. **[CRÍTICO] Legal/privacidad — la base de consentimiento actual no cubre esto, confirmado por
   el propio razonamiento del repo, no solo por argumento.** TODO-05 (resuelto 2026-08-20) resolvió
   el consentimiento apoyándose explícitamente en dos patas: (a) es el dato **propio** del
   entrenando, y (b) "la arquitectura nunca captura ni persiste **audio** — solo transcript de
   texto." El video de robos reales rompe ambas patas a la vez: las personas en el video (víctimas,
   transeúntes, otros empleados, placas/rostros visibles) nunca firmaron el contrato del entrenando
   ni obtienen nada de él, y el feature introduce exactamente la clase de media persistida (video —
   más identificable que audio) que la decisión existente se apoyaba en *no tener*. Exposición
   concreta: datos biométricos de terceros sin consentimiento (varios estados de EE.UU. tienen
   daños estatutarios por violación, ej. BIPA de Illinois); derechos de reuso de metraje que
   probablemente viene de un sistema de vigilancia de un tercero; posibles menores en cuadro;
   riesgo de re-identificación/represalia para víctimas o sospechosos retratados — todo detrás de
   endpoints con **cero RBAC** (TODO-16).
6. **[Confirmado independientemente por la fase de Eng, ver abajo] Servir scoring de "ground
   truth" de video mientras el bug de completitud (TODO-17) sigue sin arreglar no es neutral, es
   activamente dañino** — no una mejora incremental que puede esperar.
7. **Ángulo competitivo:** "build not buy" se decidió específicamente contra plataformas
   comerciales de roleplay/línea telefónica (`GOALS.md`, `roadmap-3-fases.md`) — una categoría
   distinta de "entrenamiento de reporte de testigos por video con scoring de cobertura," que sí
   existe como categoría establecida fuera de este repo (entrenadores de uso-de-fuerza/reporte de
   testigos en seguridad/law-enforcement). Reusar el veredicto anterior es citar el precedente
   equivocado — vale la pena un pase real de build-vs-buy acotado a esta capacidad específica
   antes de escribir código de upload/storage/player.

**Top 3 que el CEO independiente escalaría si solo pudiera decir tres cosas:** (1) el error de
categoría legal/privacidad — necesita un abogado antes que un ingeniero; (2) servir scoring de
video sobre el bug de completitud conocido es activamente dañino, no neutral; (3) la única
evidencia real de este equipo dice que el estímulo de texto ya funciona bien — antes de comprometer
presupuesto a una pipeline de media nueva y legalmente riesgosa, probar la hipótesis real más barato
(estímulo solo-audio) y arreglar el evaluador.

**Estas dos premisas (5 y 6) se presentan al usuario como el gate de confirmación de esta fase —
ver "Final Approval Gate."** El resto de los hallazgos informan el resto de este documento sin
requerir una pausa adicional.

## 0B — Existing Code Leverage Map

| Sub-problema | Código existente que ya lo resuelve parcial o totalmente |
|---|---|
| Modelo de datos de escenario (título/categoría/dificultad/idioma/descripción/briefing) | `core/ports.py::Scenario` + `SQLiteScenarioStore` — reusar, no reconstruir |
| Datos críticos a recolectar en la llamada | `CriticalDataPoint` (`key/label/required`) — **no reusar directamente para ground truth de video**, ver hallazgo Eng 1.1 |
| Motor de scoring / pesos configurables | `core/scoring.py::ScoreWeights` (completitud 40% / tiempo-a-dato-crítico 30% / claridad 20% / tiempo total 10%, via env vars) — el *mecanismo de comparación* (`_matches_point`) es el problema, no la estructura de pesos |
| Persistencia de incidentes reales + promoción a escenario | `IncidentOutcome`, `SQLiteIncidentStore`, `POST /incidents/{id}/promote-to-scenario` — punto de integración natural para adjuntar video de un incidente real al promoverlo, pero hoy promueve con `critical_data_points=[]` (mitad sin resolver del mismo lazo) |
| Reporte de impacto agregado | `core/impact_metrics.py` (puro, sin I/O) — extensible sin reescribir |
| Editor de escenarios (UI) | `ScenarioEditorPage.tsx` — extender el formulario existente, no construir un editor nuevo |
| Debrief post-llamada (score, categorías, transcript) | `SessionBreakdown.tsx` (reusado en `ReviewPage`/`PerformancePage`) — las nuevas métricas de video deben **plegarse** en `collected`/`missing`/`strengths`/`improvements` existentes, no crear un panel paralelo (ver hallazgo Design 5a) |
| Pipeline STT/TTS | `stt/whisper.py`, `tts/kokoro.py` — habilita la alternativa "solo-audio" como prueba de hipótesis más barata |

**¿Este plan reconstruye algo que ya existe?** No en su mayoría — la excepción es que NO se debe
reusar `CriticalDataPoint` tal cual para ground truth de video (ver Eng 1.1): necesita su propia
entidad. Todo lo demás (Scenario, scoring pesos, promote-flow, dashboard, editor) se extiende, no
se reescribe.

## 0C — Dream State Mapping

```
ESTADO ACTUAL                          ESTE PLAN                              IDEAL A 12 MESES
─────────────────                      ──────────                            ─────────────────
Escenarios de texto           --->     + escenario opcional con video    --->  El lazo de
estructurado (title/                   real/dramatizado adjunto;               retroalimentación
category/briefing/                     entrenando lo mira, luego llama         del roadmap (Fase 3)
critical_data_points)                  igual que hoy; scoring compara          cerrado de punta a
                                        contra ground truth de video           punta: post-mortems
Scoring por keyword-match               (NUEVA entidad, no reusar               reales (con video
literal contra el label                CriticalDataPoint) usando un            donde legal lo permita)
(TODO-17: 17/100 en un                 mecanismo de comparación                se promueven a
reporte perfecto)                      SEMÁNTICO, no el matcher                escenarios completos
                                        literal ya probado insuficiente         automáticamente, y el
promote-to-scenario deja                                                       impact-report puede
critical_data_points vacío             + poblar critical_data_points           correlacionar "entrenó
(mitad del lazo sin cerrar)            al promover (arregla la otra            en ESTE tipo de
                                        mitad del mismo lazo, barato)           incidente" vs. resultado
                                                                                real, no solo
Sin RBAC; cualquier sesión             + gate de rol mínimo antes de            "entrenado vs no"
autenticada lee /incidents             exponer video crudo de incidentes
```

¿Este plan mueve hacia el ideal de 12 meses? Sí, directamente — es uno de los mecanismos que el
roadmap ya nombra para Fase 3. Pero solo si las premisas 5/6 se resuelven primero; construido tal
como se pidió originalmente (video real, sin arreglar el scoring), el plan mueve *en la dirección
correcta* pero con dos defectos que lo volverían menos confiable y más riesgoso que no construirlo,
no más.

## 0C-bis — Implementation Alternatives

**APPROACH A — Ground truth autorada por humano + video como estímulo, en tablas nuevas (RECOMENDADO)**
Resumen: `Scenario` gana una referencia opcional a un video (nueva tabla `scenario_videos`, nunca
`ALTER TABLE scenarios` — ver Eng 1.2); una nueva entidad `VideoGroundTruthPoint` (con rango de
tiempo visible, no un timestamp único, y un binding a un checksum del video) reemplaza la idea de
reusar `CriticalDataPoint`; el mecanismo de comparación transcript-vs-ground-truth es **nuevo**
(no `_matches_point`), diseñado para no repetir TODO-17.
Effort: M-L (nueva tabla + puerto + adapter; nuevo módulo de comparación; UI de reproductor +
autoría de timestamps; nuevo evento WS `video.ended`).
Riesgo: Medio (mayormente aditivo sobre arquitectura existente; el riesgo real está concentrado y
nombrado: mecanismo de auth para servir video, mecanismo de comparación semántica).
Reusa: Scenario/ScenarioPort, patrón de store-por-concern (`IncidentOutcomePort` como plantilla),
promote-to-scenario, dashboard, ScenarioEditorPage.
Completeness: 9/10 — cubre estímulo, autoría, scoring y dashboard; el único hueco intencional es
diferir upload/storage de archivos grandes a una integración simple con disco local (no un CDN)
dado que hay un solo servidor LAN y un solo entrenando concurrente (NFR-11).

**APPROACH B — Ground truth auto-extraído por IA de visión**
Resumen: en vez de autoría humana, correr el video por un modelo con capacidad de visión para
extraer el ground truth automáticamente.
Effort: XL. Riesgo: Alto — sin evidencia de que se necesite, agrega una segunda capa de riesgo de
scoring (si la IA extrae mal el ground truth, el entrenando es evaluado contra una respuesta
incorrecta, en silencio) exactamente encima del mismo tipo de falla que TODO-17 ya enseñó a temer,
más costo/latencia nuevos sin validar.
Completeness: 6/10 (cubre autoría a escala, pero con un nuevo modo de falla no presente en A).

**APPROACH C — Video como contexto sin scoring nuevo**
Resumen: solo reproducir el video antes de la llamada, sin comparar nada contra él; las métricas
quedan exactamente igual que hoy.
Effort: S. Riesgo: Bajo. **Rechazado como no-alternativa real**: contradice explícitamente lo que
el usuario pidió ("obtener otras métricas," "evaluar qué tan completa y precisa fue la
comunicación") — se incluye solo para mostrar el piso, no como opción viable.

**APPROACH D (del CEO independiente) — Validar la hipótesis primero con estímulo solo-audio**
Resumen: antes de construir video, probar la hipótesis real ("estímulo más realista → mejor
transferencia") con un estímulo de audio (TTS leyendo un relato de testigo/llamante) usando
infraestructura ya existente (`tts/kokoro.py`, `stt/whisper.py`) — sin nueva categoría de
consentimiento ni de almacenamiento de media.
Effort: S. Riesgo: Bajo.
**No se auto-decide como sustituto de A** — el usuario ya tiene el activo real (biblioteca de
casos de video) y una necesidad de negocio concreta, no una hipótesis a validar; anular esa
dirección explícita a favor de un experimento sería exactamente lo que las reglas de /autoplan
prohíben (la dirección del usuario es el default, los modelos deben argumentar el cambio, no al
revés). Se registra como alternativa de menor riesgo/costo por transparencia, y como el
**primer paso recomendado si la Premisa 5 (legal) resulta bloqueante a corto plazo** — permite
seguir avanzando valor real mientras se resuelve la parte legal del video.

**RECOMENDACIÓN:** Approach A, con la arquitectura de tablas nuevas (no `ALTER TABLE`) y mecanismo
de comparación nuevo (no `_matches_point`) que exige la fase de Eng. Decisión mecánica, no de
gusto — B no es una alternativa real sin evidencia de demanda y con un modo de falla estrictamente
peor; C no cumple el pedido; D es una alternativa de secuencia (qué hacer primero si el gate legal
tarda), no un sustituto.

## Scope Decision (SELECTIVE EXPANSION)

**Complexity check:** el plan toca ~10-12 archivos (`core/ports.py`, nueva tabla+store de video,
`core/scoring.py` fix de TODO-17, nuevo módulo de comparación semántica, `server/app.py` rutas
nuevas + evento WS, `IncidentOutcome`+`sqlite_incident_store.py` para el campo de video en
promote, `ScenarioEditorPage.tsx`, nuevo componente de reproductor + gate pre-llamada compartido,
`SessionBreakdown.tsx`, `types.ts`/`api.ts`, `TODOS.md`) — por encima del umbral de 8 archivos que
SELECTIVE EXPANSION marca como señal de complejidad. Es una señal correcta, no una falsa alarma:
esto es una feature real (nueva entidad de datos + nueva superficie de seguridad + nuevo mecanismo
de scoring), no una pantalla nueva sobre un dominio que ya existe.

**Recorte auto-decidido (P3 pragmático, sin tocar el objetivo del usuario):** diferir la autoría de
video vía **upload** (endpoint de subida, límites de tamaño/tipo, storage adapter) a una iteración
posterior; para v1, el video se coloca en disco por quien administra el servidor (ruta manual) y el
escenario solo referencia esa ruta por id — corta 2-3 archivos (endpoint de upload, validación de
archivo, UI de file-input) sin bloquear la experiencia del entrenando ni el scoring. Esto es un
recorte de *mecanismo de carga*, no de la feature en sí — se puede añadir el upload real cuando el
volumen de escenarios de video lo justifique.

**No es un recorte válido:** diferir el fix de TODO-17 o el mecanismo de auth para servir video —
ambos son prerrequisitos duros confirmados independientemente por dos voces (CEO + Eng), no trabajo
que se pueda separar sin que la feature funcione mal o abra un agujero de seguridad real.

## CEO DUAL VOICES — CONSENSUS TABLE

Codex no disponible en esta máquina (`codex: not found`) — voz única, Claude subagent
independiente, tag `[subagent-only]`.

```
═══════════════════════════════════════════════════════════════════
  Dimensión                                Claude subagent   Consenso
  ──────────────────────────────────────── ───────────────── ─────────
  1. ¿Premisas válidas?                     NO (2 rotas)      [subagent-only]
  2. ¿Problema correcto a resolver?          Parcial           [subagent-only]
  3. ¿Alcance bien calibrado?                Sí, con gates     [subagent-only]
  4. ¿Alternativas suficientemente exploradas? NO (inicialmente) [subagent-only]
  5. ¿Riesgos competitivos/de mercado cubiertos? Parcial        [subagent-only]
  6. ¿Trayectoria a 6 meses sana?             NO sin gates      [subagent-only]
═══════════════════════════════════════════════════════════════════
```
N/A para "CONFIRMADO por ambos" — solo una voz de IA disponible; los hallazgos de severidad
crítica/alta de esa única voz se tratan igual que si fueran consenso, no se descartan por
"faltar la segunda opinión" (regla de degradación de /autoplan).

## NOT in scope (esta iteración)

- Extracción automática de ground truth por IA de visión (Approach B) — sin evidencia de demanda,
  candidato a TODOS.md como contingencia futura.
- Upload de video por UI (queda para una iteración posterior, ver Scope Decision).
- RBAC completo (roles manager/HR reales) — TODO-16 ya lo trackea; este plan solo exige un gate
  mínimo antes de exponer video crudo de incidentes, no el sistema de roles completo.
- Redacción automática de rostros/placas — si legal exige redacción (ver gate), es su propio
  workstream, no parte de esta iteración.
- Soporte bilingüe, concurrencia >1, multi-sitio — ya descartados por el roadmap (NFR-11, NFR-12).

## Qué ya existe (resumen para no reconstruir)

Ver tabla completa en 0B arriba. En una línea: el modelo de escenario, el motor de scoring (pesos),
el flujo de promoción de incidentes, el dashboard de impacto y el editor de escenarios ya existen y
se extienden — solo el almacenamiento/reproducción de video y el mecanismo de comparación semántica
son código nuevo real.

---

# Design Review

Corrido por un subagente de diseño independiente (ciego a la fase CEO), leyendo
`HomePage.tsx`, `ScenariosPage.tsx`, `CallPage.tsx`, `ReviewPage.tsx`/`SessionBreakdown.tsx`,
`ScenarioEditorPage.tsx`, `ImpactPage.tsx`, `PerformancePage.tsx`, `types.ts`, `ScoreRing.tsx`.

## Hallazgos (severidad propia del subagente)

1. **[Alto] Jerarquía de información.** Un paso de "ver el video" pantalla-completa y separado
   es correcto; video visible *durante* la llamada es incorrecto (convertiría el ejercicio en
   "leer en voz alta," destruyendo lo que se mide — recordar bajo presión). Hay **dos puntos de
   entrada** hoy que arrancan la llamada de forma síncrona sin paso intermedio
   (`HomePage.tsx:12-15`, `ScenariosPage.tsx:11-17`) — un build naive duplicaría la lógica de
   "¿tiene video? mostrar gate : ir directo a la llamada" en ambos lugares. **Fix:** un solo
   componente/ruta de gate pre-llamada compartido por ambos puntos de entrada.
2. **[Crítico] Estado vacío (sin video) es el default y el más riesgoso de romper.** Todo
   escenario existente hoy no tiene video, y seguirá siendo la mayoría por mucho tiempo — debe
   ser invisible: sin placeholder de "no hay video," continuar directo al flujo de hoy. Si
   `HomePage.start()` y `ScenariosPage.launch()` no quedan ambos explícitamente guardados, esto
   regresiona cada escenario de texto existente.
3. **[Alto] Otros estados faltantes:** carga/buffering (sin precedente en este código — solo hay
   texto plano de "Loading…"); error de reproducción (con reintento + una salida explícita
   "Omitir video, iniciar llamada" — nunca enmarcada como que el entrenando falló en algo);
   transición video→llamada (**rechazar auto-avance** — el fin del video no debe arrancar la
   llamada automáticamente; permitir rebobinar/re-ver antes de empezar, pero una vez presionado
   "Iniciar llamada" el paso de video se cierra, igual que en la realidad no se puede rebobinar el
   robo que se está reportando).
4. **[Crítico] Arco emocional / seguridad psicológica — el hallazgo más consecuente.** El
   producto ya tiene un principio documentado y sin resolver: un corte instantáneo a un score
   puede sentirse punitivo
   ([police-call-training-simulator.md:262-264](./police-call-training-simulator.md),
   [roadmap-3-fases.md:72-73](./roadmap-3-fases.md)). Este feature lo agrava en ambos extremos:
   antes de la llamada (ver contenido perturbador sin ningún respiro antes de tener que actuar
   bajo evaluación en vivo) y después (nuevas categorías como "omisiones específicas" se leen
   como "lo viste pasar y aun así no lo notaste" — un juicio de carácter, no de habilidad;
   "tiempo de reacción" se siente como un test de reflejos encima de un video perturbador).
   **Fix concreto:** un interstitial de calma explícito y no-auto-avanzante después del video
   ("Tomate un momento. Cuando estés listo, reportalo."); plegar las omisiones nuevas dentro de
   las listas `collected`/`missing` ya existentes en `SessionBreakdown.tsx:42-43` (mismo peso
   visual, mismo tono, cero panel nuevo alarmante — el modelo de datos ya soporta esto sin UI
   nueva: `Evaluation.collected`/`missing` en `types.ts:46-47`); si se muestra latencia, como nota
   cualitativa dentro de "Performance Notes" (`strengths`/`improvements`), nunca como un número de
   cronómetro junto al score ring.
5. **[Alto] Especificidad — el pedido sigue siendo un patrón genérico, no UI concreta.** Dónde
   vive el paso de "ver" (¿ruta nueva? ¿sub-estado de CallPage? ¿modal?) queda sin decidir; contra
   qué se mide "cobertura de lo visible" no tiene anclaje temporal en el `{key, label, required}`
   plano de hoy (`ScenarioEditorPage.tsx:144-152`); "real vs. dramatizado" se trata como
   intercambiable cuando cargan peso psicológico distinto y probablemente necesitan tratamiento de
   copy/warning distinto.
6. **[Alto] Decisiones que van a perseguir al implementador si quedan ambiguas:** (a) cobertura de
   video debe plegarse en los arrays `collected`/`missing` existentes, NO generar un panel
   "Comparación de Video" paralelo (ruido visual, misma info dos veces con lenguaje visual
   distinto); (b) autoría de ground truth para managers no-técnicos: **no** un scrubber de
   timeline desde cero — un input simple de "segundos en el clip" + botón "previsualizar en este
   momento" (salta el `currentTime` del video), reusando el layout de fila que ya existe; (c) si
   el video se puede re-ver en el debrief, debe ser un "Ver de nuevo" colapsado y opt-in, nunca
   auto-expandido junto al transcript — lo contrario convierte "reportaste de memoria" en
   "comparar en retrospectiva," una tarea completamente distinta a la que se evaluó.
7. **[Alto] Accesibilidad/inclusión.** Video-solo es un problema real para un entrenando
   sordo/hipoacúsico o con baja visión, y también para cualquiera en una oficina abierta que no
   puede reproducir audio de un video de robo en voz alta — subtítulos no son opcionales si el
   audio del video lleva contenido relevante para el ground truth. El briefing de texto
   (`ScenarioEditorPage.tsx:135-137`) debe seguir siendo una opción de primera clase ("Ver video" /
   "Leer briefing" como dos botones de igual peso, no un link pequeño de "omitir"). **El hallazgo
   más filoso:** puntuar "cobertura de lo visible" penaliza en silencio a quien tomó el camino
   accesible de texto (no tiene contenido visual contra qué medirse) — esto debe resolverse
   explícitamente (las métricas de video simplemente no aplican/no se muestran si el entrenando
   tomó el camino de texto), no puede quedar como lo que sea que el implementador construya por
   default.

**Top 3 que el diseñador independiente escalaría:** (1) el mismo riesgo de scoring que el CEO —
plegar sobre `_matches_point` reproduce TODO-17 a mayor costo emocional ("no mencionaste ni el auto
de huida," a alguien que sí lo mencionó, con otras palabras); (2) la seguridad psicológica se
agrava en ambos extremos del flujo, sobre un problema que el producto ya reconoce sin resolver;
(3) sin un gate compartido + un input simple de autoría, esto se construye dos veces mal (lógica de
gate duplicada en dos entry points, y un scrubber de timeline sobre-construido para managers
no-técnicos).

## Litmus Scorecard (7 dimensiones, 0-10)

| Dimensión | Score | Nota |
|---|---|---|
| Jerarquía de información | 6/10 | Correcta en concepto (paso separado, no durante la llamada); falta el gate compartido |
| Cobertura de estados | 3/10 | Vacío/carga/error/transición todos sin definir en el pedido original |
| Arco emocional / seguridad psicológica | 2/10 | Agrava un problema ya documentado y sin resolver, en ambos extremos |
| Especificidad de UI | 3/10 | Sigue siendo patrón genérico ("video player" + "score") |
| Consistencia con patrones existentes | 7/10 | Plegar en `collected`/`missing` es directo; el input de autoría puede reusar el layout de fila actual |
| Accesibilidad | 3/10 | Sin subtítulos, sin paridad explícita texto/video en el pedido original |
| Confianza/transparencia del scoring | 2/10 | Depende enteramente de resolver TODO-17 primero (ver fase Eng) |

**Promedio: 3.7/10 en el pedido tal como llegó** — no porque la idea sea mala, sino porque llegó
como concepto, no como diseño. Las secciones de arriba (Fix concreto en cada hallazgo) son el path
a subir ese número antes de implementar.

---

# Eng Review

Corrido por un subagente de ingeniería independiente (ciego a las fases previas), que leyó el
código real y **corrigió una premisa** que se le dio: `test_microphone.py` no está roto hoy
(106/106 tests pasan en la suite actual; el bug documentado en el design doc de origen ya se
arregló). Se registra la corrección en vez de fabricar un hallazgo para calzar con la premisa
original — el resto de este documento adopta esa corrección.

## Hallazgos

**1.1 [CRÍTICO] Arquitectura — no reusar `CriticalDataPoint` para ground truth de video.**
`CriticalDataPoint` (`core/ports.py:78-81`) es `key/label/required`, evaluado por keyword-matching
literal (`core/scoring.py:118-124`). Ground truth de video necesita un rango de tiempo visible (no
un instante único — "placa visible 0:12–0:19"), un binding a un checksum del video (para que un
recorte no desincronice los timestamps en silencio), y un mecanismo de comparación distinto. Un
campo `visible_at_seconds` pegado al dataclass existente, reusado para dos propósitos, deja sin
representación limpia un escenario con video pero sin briefing-based critical data, o viceversa.
**Fix:** nueva entidad (`VideoGroundTruthPoint`) y una tabla nueva, no un campo pegado a `Scenario`.

**1.2 [CRÍTICO] `CREATE TABLE IF NOT EXISTS` es no-op contra una tabla que ya existe — agregar una
columna a `scenarios` rompe en producción, invisible en tests.** Los cuatro stores
(`sqlite_scenario_store.py:24-36` y hermanos) corren esa DDL una vez por arranque de proceso. Cada
test usa un `tmp_path` nuevo, así que **nunca** atraparía esto — pero `sessions.db` real en la caja
RTX ya tiene una tabla `scenarios` sin la columna nueva (Gate 0 ya generó datos reales, TODO-04/08).
El primer INSERT/UPDATE que nombre la columna nueva tira `sqlite3.OperationalError` en producción,
no en CI. La justificación explícita del código para saltar migraciones ("no hay datos reales que
migrar," `sqlite_scenario_store.py:6`) está caducando justo cuando este feature se construiría.
**Fix:** nunca `ALTER` una tabla existente para este feature — toda referencia nueva de video va en
una **tabla nueva** (`CREATE TABLE IF NOT EXISTS scenario_videos` sí es seguro contra un archivo
vivo porque no toca `scenarios`). Si en algún momento un `ALTER` real es inevitable en otro lado,
este hallazgo es la razón para por fin agregar un `schema_version` + runner de `ALTER` idempotente
— no dejar que pase la primera vez en silencio.

**1.3 [Alto]** Seguir la convención propia del repo: un `VideoPort` + `SQLiteVideoStore` nuevo,
apuntando al mismo `sessions.db` compartido, igual que `IncidentOutcomePort`/`SQLiteIncidentStore`.
El riesgo no es "una tabla más" — es guardar los **bytes** del video en ese archivo (ver 2.1).

**1.4 [Medio]** `score_session` tiene un contrato de forma exacta con el frontend
(`core/scoring.py:62`). Agregar claves nuevas (cobertura de video, latencia) deja cada
`evaluation_json` ya persistido sin esas claves para siempre — el dashboard debe tolerar claves
faltantes en sesiones históricas, no asumir la forma nueva en todos lados.

**2.1 [Alto]** No guardar bytes de video como BLOB en el `sessions.db` compartido — multiplica el
riesgo para cada otro store que ya vive ahí (sin pooling, sin backup más allá de estar en
`.gitignore`). **Fix:** bytes en disco (`./video_storage/{uuid}.mp4`), solo path/checksum/metadata
en SQLite.

**2.2 [Alto]** Upload interrumpido a medio camino: nada en este stack maneja escrituras parciales
hoy. **Fix:** escribir a un path temporal → probar/checksum → rename atómico → solo entonces
commitear la fila de DB que lo referencia.

**2.3 [Alto]** Referencias colgantes al borrar: `DELETE /scenarios/{id}` ya deja
`SessionRecord.scenario_id` colgante sin cascada (patrón existente, tolerado); un video agrega el
mismo riesgo de string colgante **más** una fuga real de bytes en disco si nada borra el archivo.
**Fix:** cascade-delete explícito del archivo+fila al borrar el escenario, o una política
"huérfanos se limpian después" explícitamente documentada — no silencio.

**2.4 [Medio]** Sin validación de formato/codec en ningún input de este repo hoy. Mínimo: probar
contenedor/codec en el servidor antes de aceptar, y `duration_seconds` calculado por el servidor
(nunca confiado del cliente), porque la matemática de latencia de reacción depende de confiar en
ese número.

**2.5 [Medio]** Los caminos nil/vacío deben imitar el precedente ya existente en
`core/scoring.py:130-131`/`:80-81` — "ground truth existe pero no hay video," "hay video pero cero
puntos de ground truth," "archivo de video referenciado pero falta en disco" deben ser estados
explícitos de **no-aplicable** (excluidos del score ponderado, no puntuados en 0% en silencio), y
no deben tirar abajo una sesión WS en vivo.

**3.1 [Alto]** `promote-to-scenario` hoy redacta un `Scenario` con `critical_data_points=[]` desde
`incident.notes` (string plano). No existe campo de video en `IncidentOutcome` hoy. "Adjuntar el
video de un incidente real al promoverlo" extiende **dos** superficies de esquema
(`Scenario` e `IncidentOutcome`), no una — necesita su propio test de ida y vuelta.

**3.2 [Alto]** Ningún test ejercita la topología real de producción: los cuatro stores compartiendo
un archivo, sin `busy_timeout` en ninguna conexión `sqlite3.connect()`. Un quinto store (video) hace
cinco-en-un-archivo. Vale un test de regresión **independiente del video**: abrir los cinco stores
contra un mismo archivo temporal, golpearlos concurrentemente, confirmar que no hay
`database is locked` — autoría de ground truth ocurriendo mientras una sesión de llamada en vivo
escribe es exactamente el primer escenario real que dispararía esto.

**4.1 [CRÍTICO] La implementación "obvia" de servir video tira abajo el único mecanismo de auth de
la app.** Toda ruta REST requiere `Depends(_bearer_claims)` (`server/app.py:159-166`) — un token
bearer HMAC. Pero un `<video>` HTML no puede adjuntar un header `Authorization` a su GET. El
atajo que se ve obvio — montar `StaticFiles`, o pasarle al frontend un path/URL crudo — evita ese
límite por completo, reabriendo exactamente el boundary que ADR-0008/NFR-04 cerraron. **Fix:**
tokens firmados de corta duración por-request para una ruta de streaming dedicada, o
fetch-como-blob con el header bearer + `URL.createObjectURL` en el frontend.

**4.2 [CRÍTICO] TODO-16 (sin RBAC) se vuelve categóricamente peor.** TODO-16 ya marca que
cualquier supervisor autenticado puede leer post-mortems de texto de `/incidents`, pensados
conceptualmente para managers/RRHH. Adjuntar **video crudo de un robo real** a esa misma superficie
sin restricción es un orden de exposición distinto al texto. Esto debería bloquear el feature, no
volver a archivarse como el mismo TODO pendiente que ya es.

**4.3 [Alto]** Path traversal: cualquier implementación que acepte un filename/path influenciado
por el cliente es un vector. **Fix:** claves opacas generadas por el servidor únicamente.

**4.4 [Alto]** Sin límites de tipo/tamaño de archivo en ningún input de este repo hoy — video es el
primer tipo de input donde esa ausencia causa agotamiento real de recursos (un upload sin límite
puede llenar el mismo disco que hostea `sessions.db`, certificados TLS, y los pesos de Whisper/Kokoro
en la única caja RTX).

**5(a) [CRÍTICO] Pegar scoring de cobertura de video sobre `_matches_point` es insostenible — no es
especulativo.** TODO-17 es evidencia medida: matching literal por label puntuó un transcript
perfectamente correcto en 17/100. Hechos de video ("el sospechoso llevaba una campera roja")
tienen aún menos overlap léxico con un label corto que los `critical_data_points` actuales — reusar
el mismo matcher reproduce y probablemente amplifica esa falla exacta, enseñando activamente la
lección equivocada (contradice directamente la causa raíz confirmada en TODO-09: falta de datos a
la mano, no falla en recitar labels). **Esto no debe salir a producción sobre keyword matching.**

**5(b) [Alto]** "Anclado a video" no es "agregar un campo de timestamp" — requiere un activo de
video con su propio ciclo de vida de fallas, rangos de visibilidad (no instantes), un binding por
checksum, y la misma estructura duplicada en `IncidentOutcome` para el camino de promoción.

**5(c) [Alto]** "Tiempo de reacción" necesita un reloj que el sistema no lleva hoy. `started_at` se
fija en `call.start`; nada trackea hoy cuándo terminó el video pre-llamada. Un entrenando puede ver
el video, pausar, tomarse un café, y después empezar la llamada — confundir "tiempo desde inicio de
llamada" con "tiempo desde que terminó el video" es simplemente incorrecto. **Fix:** un evento WS
nuevo (`video.ended`), sellado por el reloj del servidor (mismo criterio que NFR-08 ya exige),
encadenado a un campo nuevo en `SessionRecord` — plomería genuinamente nueva, no un valor derivado.

**Top 3 que Eng escalaría:** (1) 5(a) — bloquea el lanzamiento de la métrica hasta diseñar un
mecanismo de comparación semántico con su propio análisis de costo/latencia; (2) 4.2 — resolver al
menos un gate de rol grueso antes de que esto salga, no solo re-archivar TODO-16; (3) 4.1 — la
implementación naive de servir video rompe silenciosamente el único boundary de auth de esta app.

## ASCII Component Diagram

```
                    ┌───────────────────────────┐
                    │  UI de autoría (manager)    │  (nuevo; necesita gate de rol — TODO-16)
                    │  (timestamps de ground truth)│
                    └─────────────┬─────────────┘
                                  │ REST (nuevo)
                                  ▼
┌───────────────┐   promote    ┌───────────────────────┐   attach    ┌─────────────────────┐
│ IncidentOutcome│─────────────▶│  Scenario (existente)  │◀───────────│ NUEVO: VideoAsset     │
│ (existente;    │  (existente,│  core/ports.py:84-96    │  reference │ store (nuevo port +   │
│  +campo video, │   extendido)│  critical_data_points   │            │ SQLiteVideoStore),    │
│  nueva sup. de │             │  SIN CAMBIOS             │            │ archivo en disco, solo│
│  esquema)      │             └────────────┬────────────┘            │ path/checksum/duración│
└───────────────┘                           │                        │ en sqlite compartido  │
                                             │ referencia             └──────────┬─────────────┘
                                             ▼                                    │ probe/validación
                              ┌──────────────────────────┐                        │ server-side
                              │ NUEVO: VideoGroundTruth    │◀───────────────────────┘ (nunca confiar
                              │ (tabla propia; rangos      │                          input del cliente)
                              │  con timestamp, NO la forma│
                              │  reusada de CriticalDataPoint)│
                              └─────────────┬──────────────┘
                                            │ leído al momento del score
                                            ▼
       ┌────────────────────────────────────────────────────────┐
       │ WS /ws/session/{id}  (existente, extendido)               │
       │ NUEVO evento: video.ended → timestamp de reloj-servidor  │
       │ (nada hoy captura "cuándo terminó el video pre-llamada")  │
       │ ⚠ servir el video en sí NO debe ser un path estático crudo│
       │   — <video> no puede mandar el header bearer (hallazgo 4.1)│
       └───────────────────────┬────────────────────────────────┘
                                │ transcript + timestamps
             ┌──────────────────┴───────────────────┐
             ▼                                      ▼
 ┌─────────────────────┐              ┌───────────────────────────┐
 │ core/scoring.py       │              │ NUEVO: video_scoring.py     │
 │ (existente, arreglar   │              │ comparación semántica —     │
 │ TODO-17 aquí también — │              │ NO reusar _matches_point    │
 │ beneficia TODO escenario)│           │ (hallazgo 5a: ya probado     │
 │                        │              │  insuficiente)              │
 └───────────┬────────────┘              └──────────────┬──────────────┘
             └───────────────────┬──────────────────────┘
                                 ▼
                  ┌──────────────────────────┐
                  │ SessionRecord.evaluation  │  (forma de dict existente —
                  │ (extender con cuidado;    │   verificar que el dashboard
                  │  filas viejas sin claves) │   tolere claves faltantes)
                  └─────────────┬─────────────┘
                                 ▼
                  ┌──────────────────────────┐        ┌───────────────────────┐
                  │ Dashboard / frontend       │        │ core/impact_metrics.py │
                  │ (existente, plegar en       │        │ (existente, puro —      │
                  │  collected/missing, NO      │        │  sin tocar salvo que    │
                  │  panel paralelo)             │        │  cobertura de video se  │
                  └──────────────────────────┘        │  pliegue en trained/    │
                                                        │  untrained)              │
                                                        └───────────────────────┘

El boundary de auth (bearer/HMAC, ADR-0008) debe envolver: endpoint de referencia de video, ruta
de servir/streamear video, y /incidents una vez que pueda llevar video real de incidentes
(TODO-16 — hoy no lo hace).
```

## Test Diagram + Plan de tests

Ver artefacto completo: `~/.gstack/projects/hhce2303-SIG-Agent/hcruz-master-test-plan-20260821-000315.md`

Resumen de gaps que un implementador probablemente se salte:
- Regresión de topología compartida (5 stores en 1 archivo, concurrencia real) — independiente del
  video, vale la pena como test propio.
- Ida y vuelta completo de promote-to-scenario con video adjunto (crear incidente con video →
  promover → confirmar que el escenario nuevo referencia el mismo archivo sin duplicarlo →
  confirmar que borrar el incidente después no deja huérfano ni borra dos veces).
- Rechazo de upload con formato/codec no soportado (4xx, no aceptado-y-falla-después).
- Video referenciado pero ausente en disco al momento del score → estado no-aplicable, no crash.
- Cascade-delete (o política de huérfanos documentada) al borrar un escenario con video.
- Ruta de servir video requiere el mismo bearer que toda otra ruta — test explícito de que un
  request sin token es rechazado (previene la regresión más probable: "funciona en el navegador
  del dev porque el navegador ya tenía la sesión abierta").

## Failure Modes Registry

| Modo de falla | Detectado por | Severidad | Mitigación |
|---|---|---|---|
| Scoring de cobertura de video reproduce TODO-17 (falsos negativos en reportes correctos) | CEO + Eng (independiente) | Crítico | Mecanismo de comparación semántico nuevo, no `_matches_point`; bloqueante de lanzamiento |
| `<video>` no puede mandar bearer header → boundary de auth se rompe si se sirve como static path | Eng | Crítico | Tokens firmados de corta duración o fetch-as-blob |
| Video real de robo expuesto sin RBAC (TODO-16 empeora) | CEO + Eng (independiente) | Crítico | Gate de rol mínimo antes de exponer video crudo de incidentes |
| `ALTER TABLE`/columna nueva en `scenarios` con datos reales ya existentes | Eng | Crítico | Solo tablas nuevas, nunca alterar `scenarios` |
| Consentimiento de terceros en video real (víctimas, transeúntes) no cubierto por la base legal actual | CEO | Crítico | Ver Final Approval Gate — requiere decisión de negocio/legal explícita |
| Upload interrumpido deja referencia a archivo a medio escribir | Eng | Alto | Write-temp → checksum → rename atómico → commit DB |
| Borrar escenario deja archivo de video huérfano en disco | Eng | Alto | Cascade-delete explícito o política documentada |
| "Tiempo de reacción" medido desde el reloj equivocado (call.start vs. video.ended) | Eng | Alto | Nuevo evento WS `video.ended`, reloj de servidor |
| Métrica de cobertura de video penalizando en silencio a quien tomó el camino de texto (accesibilidad) | Design | Alto | Métricas de video no aplican/no se muestran si no hubo video en la sesión |
| Transición video→score agrava un problema de seguridad psicológica ya documentado sin resolver | Design | Crítico | Interstitial de calma, no auto-avance, plegar en UI existente |

## Completion Summary (Eng)

Arquitectura: extender por tablas nuevas, no alterar `scenarios`. Scoring: nuevo mecanismo de
comparación, TODO-17 como prerrequisito duro. Seguridad: auth de video + gate de rol mínimo como
bloqueantes. Tests: 6 casos nuevos + 1 regresión de topología compartida, ninguno requiere mocks
nuevos más allá del patrón `tmp_path` ya establecido.

---

# Fase 3.5 — DX Review

**Saltada.** No se detectó alcance developer-facing: este es una herramienta interna para
supervisores de concesionario y managers, no un producto/SDK/CLI/API consumido por desarrolladores
externos, y ningún agente de IA es el usuario primario (Claude juega un personaje dentro de la
herramienta, no es el consumidor de la herramienta). Criterio de detección de la Fase 0 de
`/autoplan` no cumplido (0 de los términos developer-facing con 2+ matches).

---

# Decision Audit Trail

| # | Fase | Decisión | Clasificación | Principio | Racional | Rechazado |
|---|------|----------|----------------|-----------|----------|-----------|
| 1 | CEO | Saltar `/office-hours` y sintetizar el rough plan directamente | Mecánica | P6 bias toward action | El pedido ya trae problema/evidencia/alcance concretos | Ofrecer `/office-hours` primero |
| 2 | CEO | Approach A (ground truth humano, tablas nuevas) sobre B (IA de visión) | Mecánica | P1 completeness + P5 explicit | B agrega un modo de falla nuevo sin evidencia de demanda | Approach B |
| 3 | CEO | Approach C (video sin scoring) rechazado como no-alternativa | Mecánica | — | Contradice el pedido explícito del usuario | — |
| 4 | CEO | Approach D (validar con audio primero) registrado, no sustituye A | Mecánica | Dirección del usuario es el default | El usuario ya tiene el activo real; no hay hipótesis que validar | Redirigir a D como sustituto |
| 5 | CEO | Diferir upload UI a iteración posterior (video colocado manualmente para v1) | Taste → resuelta por P3 | P3 pragmático | Corta 2-3 archivos sin bloquear la experiencia del entrenando | — |
| 6 | CEO | Fix de TODO-17 y auth de video: NO diferibles | Mecánica | P2 boil lakes (blast radius) | Confirmado independientemente por 2 voces (CEO+Eng) como bloqueante duro | Diferir a TODOS.md |
| 7 | Eng | Nueva entidad `VideoGroundTruthPoint`, no reusar `CriticalDataPoint` | Mecánica | P5 explicit over clever | Reusar conflaciona dos fuentes de hechos con ciclos de vida distintos | Extender CriticalDataPoint con un campo |
| 8 | Eng | Tablas nuevas, nunca `ALTER TABLE scenarios` | Mecánica | — (hecho de corrección, no gusto) | `CREATE TABLE IF NOT EXISTS` es no-op en tabla ya existente con datos reales | Alterar la tabla existente |
| 9 | Eng | Servir video con tokens firmados / fetch-as-blob, no static path crudo | Mecánica | — (única respuesta correcta dado el boundary de auth existente) | `<video>` no manda header bearer; static path rompe ADR-0008 | Static file mount directo |
| 10 | Eng | Mecanismo de comparación nuevo para scoring de video, no `_matches_point` | Mecánica | P1 completeness (evitar daño medido) | TODO-17 es evidencia medida de que el matcher literal falla en reportes correctos | Reusar `_matches_point` |
| 11 | Design | Cobertura de video se pliega en `collected`/`missing` existentes | Mecánica | P4 DRY + P5 explicit | Evita panel paralelo con la misma info en lenguaje visual distinto | Panel "Comparación de Video" nuevo |
| 12 | Design | Un solo gate pre-llamada compartido entre `HomePage` y `ScenariosPage` | Mecánica | P4 DRY | Dos entry points existen hoy; duplicar la rama es un smell conocido | Gate duplicado por página |
| 13 | Design | Interstitial de calma no-auto-avanzante entre video y llamada | Mecánica | P1 completeness (seguridad psicológica ya es un objetivo de calidad nombrado) | Compuesto sobre un riesgo ya documentado sin resolver | Auto-avance al terminar el video |
| 14 | DX | Fase 3.5 saltada | Mecánica | — | Sin alcance developer-facing detectado | — |
| 15 | Gate | Premisas 5 (legal/consentimiento de terceros) y 6 (scoring sobre bug conocido) NO se auto-decidieron | Taste/User Challenge | Ambos voces coinciden en riesgo de seguridad/legal, no solo preferencia | Ver Final Approval Gate | Auto-aprobar y proceder sin gate |

---

# TODOS.md — Actualizaciones propuestas

Este plan requiere agregar 3 TODOs nuevos y anotar 2 existentes. Ver diff aplicado a
`docs/architecture/TODOS.md` en el mismo commit que este documento.

---

# Final Approval Gate

**Premisa de fuente de video — RESUELTA por el usuario (2026-08-21):** legal/RRHH ya evaluó y
aprobó específicamente el uso de video real de casos de robo (no solo el consentimiento general
de TODO-05, que no lo cubría). Se registró en TODO-18 con la misma nota honesta que TODO-05 usa
para este tipo de decisión: es la palabra del usuario en esta sesión, no una revisión legal
adjunta a este repo. Con esto, los escenarios de video pueden usar metraje real desde v1 —
**sujeto a que TODO-16 (gate de rol mínimo) y TODO-19 (auth de servir video) estén implementados
antes de exponer ese video**, no después. Esa condición no es una decisión de negocio pendiente,
es la misma consecuencia de ingeniería que ya aplicaría igual si el video fuera dramatizado.

**Premisa de scoring (TODO-17 como bloqueante duro) — no se re-litiga.** Ninguna de las dos
voces presentó una alternativa real a "arreglar el matcher antes de puntuar contra ground truth
de video" — no es una preferencia, es evitar un daño medido (17/100 en un reporte perfecto). Se
mantiene como prerrequisito de ingeniería, igual que en la sección Decision Audit Trail.

## Resumen ejecutivo

- **Alcance:** escenarios de video (real, con sign-off ya obtenido, o dramatizado) con ground
  truth anclado a timestamps, en tablas nuevas (nunca alterando `scenarios`), scoreados con un
  mecanismo de comparación semántico nuevo (no el keyword-matcher actual), integrado al
  dashboard/impact-report existente.
- **Decisiones: 15 totales** (11 mecánicas auto-decididas, 3 de gusto resueltas por principios
  explícitos sin necesidad de preguntar, 1 premisa resuelta por el usuario en este gate).
- **Bloqueantes duros antes de escribir código de producción (no de decisión, de secuencia):**
  TODO-17 (fix de scoring) y TODO-19 (auth de servir video) deben resolverse en la misma
  iteración que introduce el primer escenario de video — no se puede lanzar sin ellos sin
  reabrir exactamente los dos riesgos críticos que esta revisión encontró.
- **Gate de rol mínimo (TODO-16, versión acotada):** necesario antes de exponer video real de
  incidentes vía `/incidents` — no el RBAC completo, un gate mínimo de "quién puede ver video
  crudo de un incidente."
- **Diferido a iteración posterior:** upload de video por UI (v1 usa colocación manual de
  archivo); extracción automática de ground truth por IA de visión (sin evidencia de demanda);
  redacción automática de rostros/placas (workstream propio si legal lo exige más adelante).

## Reviews scores

- CEO: premisas legal/scoring escaladas correctamente; alternativas exploradas (A/B/C/D);
  alcance calibrado con gates explícitos.
- CEO Voices: Codex no disponible; Claude subagent independiente — 4/6 hallazgos de severidad
  alta/crítica, 0 hallazgos triviales.
- Design: litmus scorecard promedio 3.7/10 sobre el pedido *tal como llegó* (ver sección Design)
  — sube sustancialmente una vez aplicados los fixes concretos que la misma revisión especifica
  (gate compartido, estados faltantes, plegado en `collected`/`missing`, accesibilidad explícita).
- Eng: arquitectura corregida hacia tablas nuevas + mecanismo de comparación nuevo; diagrama de
  componentes y plan de tests producidos; 1 premisa del prompt corregida por evidencia real
  (`test_microphone.py` ya no está roto).
- DX: saltada — sin alcance developer-facing.

## Próximos pasos

Este plan queda listo para pasar a implementación por iteraciones, en este orden de secuencia
(no de prioridad de negocio, de dependencia técnica real):
1. Fix de TODO-17 (beneficia todo escenario existente, no solo video) + su test adversarial.
2. Tablas nuevas (`scenario_videos`, ground truth de video) + store, sin tocar `scenarios`.
3. Mecanismo de auth de servir video (TODO-19) + gate de rol mínimo (TODO-16 acotado).
4. Gate pre-llamada compartido (frontend) + interstitial de calma + plegado de métricas nuevas
   en `SessionBreakdown` existente.
5. Extensión del flujo de promoción de incidente→escenario con video adjunto.

Sugerido: `/ship` una vez que la primera iteración (1-3, el "esqueleto" sin UI de autoría todavía)
tenga tests verdes, o `/plan-eng-review` si se quiere una pasada de ingeniería más profunda sobre
el mecanismo de comparación semántica del punto 1 antes de escribir código.
