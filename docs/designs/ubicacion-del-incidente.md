# Design + Review: Ubicación estructurada del incidente (mini-mapa + evaluación de claridad de ubicación)

Generado por `/autoplan` el 2026-08-21 (sin `/office-hours` previo — ver nota de proceso abajo).
Branch: feature/video-scenarios | Repo: SIG-Agent | Base branch: master | Modo: **SELECTIVE EXPANSION**
(auto-decidido — es una extensión del modelo de escenarios y del motor de scoring ya existentes, no un
feature greenfield).
Estado: **APPROVED** (2026-08-22) — el usuario aprobó el plan tal como quedó en el Final Approval Gate:
T1 (Location fusionada dentro de "Completeness", sin barra propia) y T2 (matching contra el valor exacto
configurado, reframe de "specificity" diferido a TODOS.md) se mantienen tal como quedaron diseñados.
Implementación lista para iniciar por los Implementation Tasks de Fase 2 y Fase 3.

**Nota de proceso:** no existe un plan file previo para este feature específico. Se auto-decidió saltar
`/office-hours` (principio #6, bias toward action — mismo criterio ya aplicado en
`docs/designs/motor-de-metricas.md`). `codex` y `jq` **no están instalados** en esta máquina — las voces
duales corren en modo **`[subagent-only]`**, y el agregador de tareas JSONL queda deshabilitado.

**Nota de corrección (léase antes que el resto del documento):** el borrador inicial de este documento
(Fase 1, antes de la voz independiente) tenía **tres errores de hecho que invalidaban su propia
recomendación central**: (1) asumió que `briefing` se le muestra al trainee antes de la llamada — es
falso, no se renderiza en ningún lado del flujo de llamada (`CallPage.tsx`, `HomePage.tsx`), solo existe
en el editor de autoría y en el prompt de sistema del dispatcher-IA; (2) asumió que `motor-de-metricas.md`
seguía "en revisión, sin gate alcanzado" — es falso, ese plan está **`Estado: APPROVED`** desde la misma
sesión; (3) asumió que solo 1 de los 3 escenarios semilla ya modela "ubicación" — los 3 lo hacen
(`last_location`, `address`, `location`). Las tres correcciones cambian la recomendación de fondo (ver
0A punto 1 corregido) y se incorporan en todo el documento a partir de aquí — el razonamiento de la
Sección "CEO Dual Voices" al final de esta fase documenta el borrador original y el porqué del cambio.

## Pedido original del usuario

> "hay otro parametro que en las llamadas es muy importante, y es que tanto en tiempo real como en
> playbacks el supervisor necesita darle una direccion y contexto de donde esta succediendo el robo o la
> situacion de sospecha, esto realemente es muy importante para que cuando la policia sea enviada a los
> sitios tengan la informacion de donde buscar, entonces necesito agregar un metodo o un campo mas para
> configurar en el modulo de escenarios, puede ser algo basico no se necesita un motor de geolocalizacion
> como el de google, puede ser algo incluso ficticio, entonces un mini mapa con un flag de la ubicacion
> del suceso con la estrella de los polos, para mayor informacion y especialmente nombres de calles,
> avenidas, y demas, entonces como el agente ya tiene cargado el objetivo del mapa, cuando el usuario en
> trainning diga esta informacion tambien sera posible evaluar con que tanta claridad dio la informacion
> y que tan efectiva fue esta"

Es decir: (1) un campo de configuración de escenario nuevo — ubicación del incidente, con calles,
avenidas y referencias, representada visualmente con un mini-mapa esquemático/ficticio (flag + rosa de
los vientos), disponible tanto para escenarios en tiempo real como de playback; (2) el trainee **ya tiene
cargado** el objetivo del mapa (frase clave del usuario — asume un canal por el cual el trainee conoce la
ubicación antes de hablar); (3) evaluar si comunicó esa ubicación, con qué claridad, y qué tan efectiva
sería para que la policía llegue al sitio correcto — integrado al scoring existente.

## Problem Statement

`docs/architecture/TODOS.md` TODO-17 ya documenta, con una llamada real, el síntoma exacto de la brecha
que este pedido ataca: un trainee reportó una ubicación *inventada* ("Westfield Shopping Center") porque
**no existe hoy ningún canal en el flujo de llamada que le muestre el contexto del escenario antes de
empezar** — `briefing` (el texto narrativo del incidente) nunca se renderiza en `CallPage.tsx` ni
`HomePage.tsx`; solo alimenta el prompt de sistema del dispatcher-IA (el bot), no al trainee humano. Los
tres escenarios semilla ya modelan una noción de ubicación como **un** `CriticalDataPoint` suelto
(`last_location`/`address`/`location`, `sqlite_scenario_store.py:76-78,116-118,165-169`), sin estructura
(calle vs. cruce vs. referencia son la misma bolsa de hints) y sin ninguna representación visual — y sin
ningún canal confirmado por el que el trainee reciba esa información antes de hablar.

La frase del propio usuario — "el agente ya tiene cargado el objetivo del mapa" — asume que ese canal
existe o debe existir. No existe hoy para escenarios de texto (solo los escenarios de video tienen un
paso de pre-llamada, `PreCallVideoGate.tsx`, que sí le muestra contenido al trainee antes de empezar).
Sin ese canal, cualquier ground truth de ubicación —estructurado o no— es, en la práctica, **imposible de
cumplir**: el trainee no puede comunicar con claridad un dato que nunca recibió. Este es el hallazgo más
importante de esta revisión (0A punto 1) y determina el diseño de todo lo demás.

**Qué pasa si no hacemos nada:** el problema documentado en TODO-17 se repite indefinidamente — los
trainees siguen improvisando ubicaciones porque no se les da ninguna, y el score de "completeness" sigue
midiendo azar de improvisación, no habilidad real de comunicación. Agregar structure y un mapa sin
resolver el canal de entrega sería, literalmente, construir una respuesta correcta para un examen que
nadie puede ver antes del examen.

## 0A — Premise Challenge

1. **[CRÍTICO, corregido tras la voz independiente, y corregido DE NUEVO tras la voz de diseño] La
   premisa "ocultar el mapa al trainee, igual que `match_hints`" está invertida — el precedente de video
   dice lo contrario, y ya fue corregido una vez en producción.** El borrador inicial de esta sección
   proponía ocultar el mini-mapa por completo, igual que los `match_hints`. Es el precedente equivocado:
   en escenarios de video, el **contenido** (el video mismo) SÍ se le muestra al trainee
   (`PreCallVideoGate.tsx` lo reproduce pantalla completa antes de la llamada) — lo único que se oculta
   son los metadatos de scoring (`match_hints`, timestamps, `ScenarioVideoAccessOut`,
   `server/app.py:161-168`). La ubicación debe seguir la misma división: el **contenido** (calle, cruce,
   referencia, el mini-mapa con el flag) se le muestra al trainee en una pantalla de pre-llamada nueva —
   los `match_hints` permanecen ocultos. Sin esta pantalla nueva, la premisa original del usuario ("el
   agente ya tiene cargado el objetivo del mapa") no se cumple — hoy no existe ningún canal de
   pre-llamada para escenarios sin video. **Esto convierte lo que parecía un cherry-pick opcional en
   parte del alcance mínimo.**
   **Corrección adicional (Fase 2, hallazgo F12 de la voz de diseño):** el borrador de Fase 1 además
   asumía que la ventana de visibilidad debía ser **exclusivamente** pre-llamada, calcando "igual que
   video." Es falso incluso para video: `frontend/src/components/InCallVideoPanel.tsx` ya existe en esta
   rama y su comentario de cabecera lo dice explícitamente — "pedido explícito del usuario: poder ver el
   video DURANTE la simulación... El plan original lo dejaba fuera a propósito... se mantiene esa
   preocupación, pero como algo que el entrenando elige activamente (cerrado por default, un botón para
   abrirlo)." El usuario ya revirtió el argumento "ocultar todo durante la llamada" una vez, para la
   feature hermana. Repetirlo aquí como si fuera precedente válido sería ignorar una decisión de producto
   ya tomada. **Corrección de diseño: la ubicación sigue el mismo patrón — un `InCallLocationPanel`
   cerrado por default, con un botón opt-in ("Check the address again"), nunca mostrado automáticamente.**
   Ver cherry-pick #8 corregido en 0D.
2. **Confirmada: "no se necesita motor de geolocalización real, puede ser ficticio."** Consistente con
   los 3 escenarios semilla, que ya usan ubicaciones inventadas. Coordenadas normalizadas (0..1) dentro
   de un lienzo esquemático, no lat/long reales.
3. **[CRÍTICO, corregido] `motor-de-metricas.md` está `APPROVED`, no "en revisión."** El borrador inicial
   citaba ese plan como pendiente de su propio gate — falso, su encabezado dice explícitamente
   `Estado: APPROVED (2026-08-21) — el usuario aprobó el plan... implementación lista para iniciar por
   T1-T16`. Ese plan reemplaza el matching por keyword/hints de `_matches_point` con un LLM-judge
   post-llamada para completeness semántica, coherencia e inglés — la misma función (`score_session`)
   que este plan también extiende. Esto no bloquea este plan (construir sobre `_matches_point` hoy es
   consistente con cómo YA funciona el 100% del scoring de ground truth, incluyendo video, ADR-0010), pero
   sí determina cómo debe presentarse el ground truth de ubicación: como datos estructurados simples
   (valor + hints), no como lógica de comparación custom — para que sea trivial de re-alimentar al juez
   LLM cuando esa implementación aterrice, en vez de tener que reescribirse.
4. **[CRÍTICO, hallazgo nuevo] Fusionar 3-4 puntos de ubicación al `all_points` existente re-pesaría
   `completeness` en silencio.** Los escenarios semilla tienen ~6 `critical_data_points`. Agregar un
   punto por cada campo no vacío de ubicación (calle, cruce, referencia, zona) llevaría el denominador de
   completeness a ~10, haciendo que la ubicación por sí sola pese más que toda la categoría `clarity`
   (20%) — una decisión de re-ponderación real, no un "merge gratis" como lo presentaba el cherry-pick #1
   del borrador inicial. **Corrección de diseño:** la ubicación entra a `all_points` como **un solo**
   punto combinado (`required=True`, hints = unión de las frases de calle+cruce+referencia configuradas)
   — "¿dio el trainee al menos un dato de ubicación específico y accionable?" — no un punto por campo. El
   desglose fino (cuántos de calle/cruce/referencia se mencionaron, y cuándo) se reporta como narrativa
   cualitativa en `strengths`/`improvements`, reutilizando `_time_to_critical_data` sin cambios — igual
   patrón que `video_reaction_seconds` (nunca se vuelve categoría ponderada nueva, `scoring.py:204-230`).
5. **[Hallazgo nuevo] Etiquetas genéricas romperían el fallback de `_matches_point` — el mismo bug que
   TODO-17 ya documentó, en dirección opuesta.** `_matches_point` (`scoring.py:153-165`) cae, como último
   recurso, a "¿aparece cualquier palabra >3 caracteres de la etiqueta?" Si el punto de ubicación se
   generara con `label="Street"` o `label="Landmark"` (genérico), **la palabra suelta "calle"/"street" en
   cualquier parte del transcript marcaría el punto como cumplido** — un detector de palabras, no una
   medición real (`domestic_dispute` ya usa "street" como hint hoy, confirmando el riesgo). **Corrección
   de diseño:** el `label` del punto generado debe ser el valor configurado real (ej. `"5th Avenue"`), no
   un nombre de campo genérico — esto es automático (no requiere trabajo extra del autor) y evita el
   fallback genérico por construcción, igual que ya evita el problema cualquier `CriticalDataPoint`
   autorado con un label específico hoy.
6. **[Hallazgo nuevo] Migrar los 3 escenarios semilla no arregla producción — mismo gap que TODO-20 ya
   documenta para otra tabla.** `SQLiteScenarioStore.__init__` solo siembra si la tabla está vacía
   (`sqlite_scenario_store.py:205`) — el Gate 0 ya generó datos reales, así que editar
   `_seed_scenarios()` no cambia nada en una base ya poblada. La migración de los 3 escenarios existentes
   (retirar su `CriticalDataPoint` suelto de ubicación, reemplazarlo por `ScenarioLocation` estructurado)
   es una tarea manual de autoría vía el editor, no un cambio de código que se aplique solo — debe
   documentarse como paso de rollout, no asumirse gratis.
7. **No hay separación real de roles trainee/supervisor — corrige el punto 7 del borrador inicial.** El
   login (`app.py:292-315`) emite `supervisor`/`manager`; no existe un rol "trainee" separado ni un
   token de menor confianza — quien toma la llamada tiene, técnicamente, el mismo acceso de API que quien
   autora escenarios (`TODO-16`, PENDING, ya lo documenta a nivel de repo). El split "vista de autoría
   completa vs. vista de trainee sin hints" (igual que video) es una medida de UX anti-spoiler dentro de
   la propia pantalla de llamada, no un control de acceso — correcto y suficiente para este feature
   (mismo nivel de protección que ya tiene video hoy), no es una brecha nueva que este plan introduzca.
8. **Seguridad psicológica (`GOALS.md:23-25`).** La narrativa de "faltó el cruce/la referencia" debe ser
   coaching accionable, nunca juicio de carácter — y ahora que el trainee sí recibió la información
   (punto 1 corregido), la retroalimentación es honesta: se le puede decir que faltó algo que sí conocía,
   sin el riesgo (marcado en la revisión anterior de video) de estar corrigiendo al trainee por no
   adivinar un dato que nunca tuvo.

**Top 3 que escalaría si solo pudiera decir tres cosas:** (1) sin una pantalla de pre-llamada nueva que
muestre el mini-mapa/ubicación al trainee, el feature completo es imposible de cumplir — esto pasa de
"cherry-pick" a alcance mínimo; (2) fusionar ubicación al `all_points` existente debe ser **un** punto
combinado, no uno por campo, o re-pesa completeness en silencio; (3) `motor-de-metricas.md` ya está
aprobado (no pendiente) — el ground truth de ubicación debe modelarse como datos simples reutilizables
por el futuro juez LLM, no como lógica de comparación nueva y específica.

**Estas tres premisas (1, 3, 4) se presentan al usuario como el gate de confirmación de esta fase — ver
"Final Approval Gate."** El resto informa el resto del documento sin pausa adicional.

## 0B — Existing Code Leverage Map

| Sub-problema del pedido | Código existente que ya resuelve parte de esto | Reutilizar o reconstruir |
|---|---|---|
| Pantalla de pre-llamada que muestra contenido (no solo ground truth oculto) | `PreCallVideoGate.tsx` (líneas 1-98) — ya resuelve exactamente este problema para video: gatea `call.start` hasta que el trainee reconoce el contenido | **Reutilizar el patrón exacto**: nuevo `PreCallLocationBriefing.tsx`, mismo gate en `CallPage.tsx` antes de `startCall()`. Si el escenario tiene video Y ubicación, se muestran en secuencia (decisión de Fase 2/Design). |
| Forma de un "dato crítico" con hints de coincidencia | `CriticalDataPoint`/`VideoGroundTruthPoint` (`core/ports.py:77-89, 134-147`), comparador `_matches_point` (`scoring.py:153-165`) | **Reutilizar el mecanismo** de match_hints; un solo punto combinado de ubicación (ver 0A punto 4), no una entidad paralela compleja. |
| Persistencia sin `ALTER TABLE` (`TODO-20`) | Patrón `sqlite_scenario_video_store.py` — tabla 1:1 nueva, PK=`scenario_id` | **Reutilizar el patrón exacto**: tabla nueva `scenario_locations`. |
| Autoría de un sub-recurso opcional en el editor | `ScenarioEditorPage.tsx` sección de video (líneas 273-343) | **Reutilizar el patrón**: nueva sección "Ubicación del incidente." |
| Ocultar hints (no contenido) al trainee | `GET /scenarios/{id}/video/ground-truth` (autoría) vs. `ScenarioVideoAccessOut` (trainee, sin hints, **con** el video mismo) | **Reutilizar el mismo split** — la vista de trainee incluye calle/cruce/referencia/mapa, excluye match_hints. |
| Medir "qué tan pronto" se dio un dato | `_time_to_critical_data` (`scoring.py:181-201`), genérico sobre `all_points` | **Reutilizar sin cambios.** |
| Narrativa cualitativa sin categoría ponderada nueva | Patrón `_video_reaction_seconds` (`scoring.py:204-230`, docstring 271-274) | **Reutilizar el mismo patrón** para el desglose calle/cruce/referencia. |
| Render en dashboard de hechos "collected/missing" | `SessionBreakdown.tsx`, `Object.entries()` genérico | **Reutilizar sin cambios** para el conteo; se necesita un componente nuevo (`LocationMiniMap`, 3 modos: author/brief/review) para visualizar el mapa. |
| "Ubicación" ya insinuada, en los 3 escenarios semilla | `last_location`/`address`/`location` (`sqlite_scenario_store.py:76-78,116-118,165-169`) — **los 3**, no 1 | **Migrar los 3** (manualmente vía editor en producción, ver 0A punto 6) — retirar el punto suelto al adoptar `ScenarioLocation`, para no contar el mismo hecho dos veces. |

**¿Se está reconstruyendo algo que ya existe?** No — el único cruce con infraestructura ya construida es
el mecanismo de ground-truth/match_hints y el patrón de gate de pre-llamada de video; en ambos casos la
recomendación es reutilizar.

## 0C — Dream State Mapping

```
  CURRENT STATE                       THIS PLAN                              12-MONTH IDEAL
  ──────────────                      ─────────                              ───────────────
  Ubicación = 1 CriticalDataPoint     + ScenarioLocation estructurado         Juez LLM (motor-de-metricas,
  suelto por escenario (3/3 semilla,  (street, cross_street, landmark,        APPROVED) evalúa completitud
  sin estructura, sin canal de        city_or_zone, marker_x/y) persistido    Y ubicación con juicio
  entrega al trainee)                 en tabla nueva                         semántico — "diste una calle
                                                                              pero ambigua" — consumiendo
  CERO pantalla de pre-llamada        + PreCallLocationBriefing.tsx (nueva,   los mismos campos
  para escenarios sin video —         mismo patrón que PreCallVideoGate) —   estructurados que este plan
  TODO-17 documenta el síntoma        el trainee SÍ ve calle/cruce/           ya crea, sin rediseño.
  exacto (ubicación inventada)        referencia/mapa antes de la llamada
                                                                              Pantalla de pre-llamada
  Sin mini-mapa en ningún lado        + LocationMiniMap.tsx (3 modos:         genérica también muestra
                                       author/brief/review), 1 solo punto     `briefing` completo — cierra
  Briefing nunca se muestra al        combinado fusionado a `all_points`     TODO-17 para TODOS los datos
  trainee (gap que afecta a TODOS     (mismo mecanismo que video, ADR-0010)  críticos, no solo ubicación.
  los critical_data_points, no
  solo ubicación)                     + narrativa de claridad de ubicación
                                       (calle/cruce/referencia, cuándo) en
                                       strengths/improvements
```

## 0C-bis — Implementation Alternatives (MANDATORY)

**APPROACH A — Campos estructurados + mini-mapa de un marcador + pantalla de pre-llamada (RECOMENDADA)**
- Resumen: `ScenarioLocation` (street, cross_street, landmark, city_or_zone, additional_directions,
  match_hints, marker_x/marker_y 0..1) en tabla nueva 1:1. `ScenarioEditorPage.tsx` gana una sección de
  autoría con el mini-mapa clickeable. **`PreCallLocationBriefing.tsx` nuevo** (precedente:
  `PreCallVideoGate.tsx`) muestra el mini-mapa + calle/cruce/referencia (sin hints) al trainee antes de
  `call.start`, para escenarios con y sin video. Un solo punto de ubicación combinado se fusiona a
  `all_points` en scoring; narrativa de claridad reutiliza `_time_to_critical_data` + un helper nuevo
  `_location_narrative()`. Cherry-pick de bajo costo incluido: la misma pantalla nueva también muestra
  `briefing` (hoy nunca mostrado a nadie) — cierra TODO-17 para todos los datos críticos, no solo
  ubicación, con ~1 párrafo extra de JSX.
- Effort: **M** (human: ~3-4 días / CC: ~half day) — 1 dataclass, 1 tabla, 1 endpoint CRUD, 1 componente
  de mapa (3 modos), 1 pantalla de pre-llamada nueva, 1 sección de formulario, ~30 líneas en
  `score_session`.
- Risk: **Low** — aditivo puro; cero latencia nueva en la llamada en vivo (todo el scoring sigue siendo
  post-llamada). El único cambio de comportamiento en vivo es un gate de pre-llamada adicional — mismo
  patrón que video ya usa hoy sin incidentes.
- Pros: cumple el pedido literal (mapa + flag + rosa de los vientos + nombres de calle) **y** lo hace
  cumplible (el trainee de verdad recibe la información antes de la llamada — sin esto, el resto del
  feature no tendría sentido, ver 0A punto 1); funciona igual para tiempo real y playback sin ramas de
  código nuevas.
- Cons: el mapa es esquemático — un solo marcador, calles como texto, no geometría dibujada — aceptado
  como parte explícita de "básico"/"ficticio."
- Reutiliza: `_matches_point`, `_time_to_critical_data`, patrón `sqlite_scenario_video_store.py`, patrón
  `PreCallVideoGate.tsx`, patrón de sección condicional de `ScenarioEditorPage.tsx`, render genérico de
  `SessionBreakdown.tsx`.

**APPROACH B — Editor de mapa interactivo con calles dibujadas y múltiples marcadores**
- Resumen: lienzo tipo pizarra con segmentos de calle dibujados a mano y múltiples marcadores.
- Effort: **L/XL** (human: ~2-3 semanas / CC: ~2-3 días).
- Risk: **Med** — blast radius mucho mayor sin señal de scoring adicional (el scoring depende del texto
  dicho, no de la geometría dibujada) y sin resolver el problema real (0A punto 1) por sí sola.
- Pros: visualmente más rico.
- Cons: sobre-construye contra "básico"/"ficticio"; no resuelve el gap de canal de entrega si se
  implementa sin la pantalla de pre-llamada de Approach A.
- Reutiliza: nada nuevo de peso.

**APPROACH C — Solo campos de texto, sin mini-mapa ni pantalla de pre-llamada**
- Resumen: agregar `street/cross_street/landmark` como campos planos; sin componente visual, sin gate.
- Effort: **S** (human: ~1 día / CC: ~2h).
- Risk: **Alto en la práctica** — sin pantalla de pre-llamada, reproduce exactamente el bug de TODO-17: el
  trainee sigue sin canal para recibir el dato, así que scorearlo contra un valor que nunca vio sigue
  siendo injusto/imposible de cumplir. Esto no es solo "incumple el pedido visual" (como decía el
  borrador inicial) — es la opción que **no resuelve el problema real** identificado en 0A punto 1.
- Reutiliza: lo mismo que A menos el mapa y la pantalla de pre-llamada.

**RECOMENDACIÓN: Approach A.** No es TASTE DECISION: B sobre-construye sin pedirlo y sin señal de scoring
adicional; C, tras la corrección de 0A punto 1, ya no es "más barato pero incompleto" — es una opción que
no logra el objetivo declarado por el usuario en absoluto (evaluar comunicación de un dato que el trainee
nunca recibió). Se auto-decide A por P1 (completeness) y P5 (explicit — el mapa de un marcador es la
forma más simple que aún resuelve el problema real).

## 0D — Mode-Specific Analysis (SELECTIVE EXPANSION)

**Complexity check:** ~5 archivos de backend (`core/ports.py`, nuevo `persistence/sqlite_scenario_location_store.py`,
`server/app.py`, `core/scoring.py`, migración manual de datos vía editor — no código) + ~4 de frontend
(`ScenarioEditorPage.tsx`, nuevo `LocationMiniMap.tsx`, nuevo `PreCallLocationBriefing.tsx`,
`SessionBreakdown.tsx`, `CallPage.tsx`) + tests. Por debajo del umbral de 8 archivos que disparó revisión
completa para video, pero se ejecuta la revisión completa porque el usuario pidió `/autoplan`.

**Mínimo que logra el objetivo declarado (revisado, incluye lo que 0A movió de cherry-pick a núcleo):**
`ScenarioLocation` persistido + mini-mapa de autoría + **pantalla de pre-llamada que se lo muestra al
trainee** + un punto combinado fusionado a `all_points` + narrativa de claridad + render del mapa en modo
solo-lectura en `SessionBreakdown` para revisión post-llamada.

**Cherry-picks evaluados:**

| # | Propuesta | Blast radius | Effort | Decisión | Principio | Razonamiento |
|---|---|---|---|---|---|---|
| 1 | Pantalla de pre-llamada (`PreCallLocationBriefing`) que muestra el mini-mapa al trainee | `CallPage.tsx` + componente nuevo | S/M | **ACEPTADO — movido a alcance mínimo** | P1 | Ver 0A punto 1: sin esto el feature no es cumplible. No es expansión, es requisito. |
| 2 | Mostrar también `briefing` (texto libre) en esa misma pantalla nueva | Mismo componente, ~1 párrafo JSX | XS | **ACEPTADO** | P2 boil lakes | Mismo archivo que ya se está tocando, <1 día, cierra TODO-17 para todos los critical_data_points, no solo ubicación — dejarlo fuera sería construir la pantalla y omitir el fix más barato disponible en ese mismo lugar. |
| 3 | Un solo punto combinado de ubicación en `all_points` (no uno por campo) | `scoring.py`, mismo mecanismo que video | S | **ACEPTADO — corrige el cherry-pick #1 del borrador inicial** | P4 DRY + P5 explicit | Ver 0A punto 4 — evita re-pesar completeness en silencio. |
| 4 | Categoría ponderada nueva "Ubicación" visible por separado en el dashboard | `scoring.py` + `SessionBreakdown.tsx` | S/M | **TASTE DECISION** | — | Decisión de legibilidad/UX, no de matemática de scoring — va al gate. |
| 5 | Reutilizar `_time_to_critical_data` sin cambios | `scoring.py`, lectura | XS | **ACEPTADO** | P3 | Ya es genérico, cero código nuevo de lógica. |
| 6 | Mostrar el mini-mapa (solo lectura) en `SessionBreakdown.tsx` para revisión post-llamada | Mismo componente `LocationMiniMap`, modo `review` | S | **ACEPTADO** | P1 | Sin esto el supervisor no puede comparar visualmente lo configurado vs. lo dicho. |
| 7 | Editor de mapa interactivo con líneas dibujadas (Approach B) | Alto | L/XL | **RECHAZADO** → NOT in scope | P5 | Ver Approach B. |
| 8 | Mostrar el mapa/calles al trainee **durante** la llamada en vivo, como acceso opt-in (no automático) | `CallPage.tsx` — mismo patrón que `InCallVideoPanel.tsx` | S | **ACEPTADO (corregido en Fase 2, hallazgo F12)** | P6 bias-toward-action + consistencia de producto | El borrador original lo rechazaba asumiendo "igual que video" — falso: `InCallVideoPanel.tsx` ya existe, cerrado por default con un toggle opt-in, tras un pedido explícito del usuario que revirtió esa misma restricción para video. Repetir el argumento aquí ignoraría una decisión de producto ya tomada. Se acepta en la misma forma: `InCallLocationPanel`, cerrado por default, un botón ("Check the address again"), nunca automático — no invalida el ejercicio porque requiere una acción deliberada del trainee, igual que hoy con el video. |
| 9 | Migración de código de los 3 escenarios semilla vía `_seed_scenarios()` | No afecta producción (0A punto 6) | — | **RECHAZADO como "fix"** → documentado como paso manual de rollout en TODOS.md | — | `_seed_scenarios()` es un no-op contra una DB ya poblada (mismo gap que TODO-20). |
| 10 | Soporte de múltiples marcadores por escenario (incidente + ruta de escape) | `ScenarioLocation` pasaría a ser lista | M | **DEFERIDO a TODOS.md** | P3 | Fuera del pedido original (singular: "la ubicación del suceso"). |
| 11 | `rubric_version` formal en `evaluation` para versionar cambios de denominador de completeness a través del tiempo | Cross-cutting — afecta a TODA feature que ya tocó `all_points` (video, y este) | M | **DEFERIDO a TODOS.md** | P3 | Riesgo real (ver hallazgo de la voz independiente) pero preexistente y cross-cutting, no exclusivo de este plan — mitigado en este plan al capitalizarlo como UN punto combinado (cherry-pick #3), no eliminado del todo. |

## 0E — Temporal Interrogation

```
  HOUR 1 (fundamentos):     ¿`PreCallLocationBriefing` es un paso separado de `PreCallVideoGate` o un
                            único componente combinado? (Separado, en secuencia: location briefing
                            primero, video gate después — decidido en Fase 2 Pass 7 F14/F15: la
                            ubicación es el contexto de la escena, el video es la evidencia del
                            incidente; el botón final "Start Call" queda en la última pantalla de la
                            secuencia, nunca duplicado.)
  HOUR 2-3 (lógica core):   ¿Cómo entra el punto combinado de ubicación a `all_points`? (Un
                            `LocationGroundTruthPoint` con `label` = valor configurado real, `match_hints`
                            = unión de calle+cruce+referencia+hints de autor, concatenado igual que
                            `video_ground_truth`, línea 109.) ¿Qué pasa si el escenario no tiene ubicación
                            configurada? (Lista vacía, cero cambio — backward compatible.)
  HOUR 4-5 (integración):   ¿Composición con escenarios de video? (Si `has_video` Y ubicación
                            configurada, secuencia: video gate → location briefing → call.start.) ¿Cómo
                            versiona el frontend sesiones históricas sin datos de ubicación? (Campo
                            opcional/null; `SessionBreakdown` oculta la subsección si falta.)
  HOUR 6+ (pulido/tests):   `test_scoring.py` necesita: ubicación no configurada, punto combinado
                            cumplido/no cumplido, mencionado tarde. `test_server.py`/frontend: gate de
                            pre-llamada bloquea `call.start` hasta reconocer, igual que el test existente
                            de video. Regresión explícita de TODO-17 con el nuevo canal de entrega
                            (¿el trainee que SÍ recibe la ubicación dejó de inventar datos?).
```
NOTA: horas de implementación humana; con CC + gstack esto comprime a fracciones de hora.

## 0F — Mode Selection (confirmado, auto-decidido)

**SELECTIVE EXPANSION** — extensión del modelo de escenarios + motor de scoring + patrón de pre-llamada ya
existentes. Cherry-picks resueltos en 0D. Se mantiene sin drift durante el resto de la revisión.

## CEO DUAL VOICES — Consensus Table

CODEX SAYS (CEO — strategy challenge): *(no disponible — codex no instalado en esta máquina)*.

CLAUDE SUBAGENT (CEO — strategic independence), leyendo el código de forma ciega e independiente: encontró
que el borrador inicial de esta fase estaba **construido sobre una premisa invertida** — proponía ocultar
el mapa al trainee (calcando el precedente equivocado de video: confundió "ocultar los hints" con "ocultar
el contenido") cuando el código confirma que `briefing` nunca llega al trainee por ningún canal hoy
(`grep` de `briefing` en `CallPage.tsx`/`HomePage.tsx`: cero resultados) — haciendo que el ground truth de
ubicación, tal como estaba planteado, fuera imposible de cumplir por diseño. También corrigió dos hechos:
`motor-de-metricas.md` está `APPROVED`, no pendiente; los 3 escenarios semilla (no 1) ya modelan
"ubicación." Y encontró un riesgo de diseño nuevo no visto en el borrador inicial: fusionar un punto por
cada campo de ubicación re-pesaría `completeness` en ~45% sin que nadie lo decidiera explícitamente, y
etiquetas genéricas (`"Street"`, `"Landmark"`) activarían el fallback de `_matches_point` como detector de
palabras sueltas. Las cuatro correcciones ya están incorporadas arriba (0A puntos 1, 3, 4, 5, 6, 7) — el
diseño recomendado cambió de "ocultar todo + un punto por campo" a "pantalla de pre-llamada nueva + un
punto combinado," que es una diferencia arquitectónica real, no un matiz.

```
CEO DUAL VOICES — CONSENSUS TABLE:
═══════════════════════════════════════════════════════════════════════════
  Dimension                              Claude(main, corregido)  Claude(subagent)  Consensus
  ───────────────────────────────────────  ────────────────────────  ─────────────────  ─────────
  1. Premises valid?                       NO (canal de entrega,     NO (mismo hallazgo, CONFIRMED
                                            tras corrección)          independiente)      (tras corregir)
  2. Right problem to solve?               SÍ, con reframing         Cuestiona el marco   CONFIRMED,
                                            (canal + scoring, no      (ver nota abajo)     con matiz
                                            solo scoring)
  3. Scope calibration correct?            SÍ (Approach A, tras      Cuestiona si vale     TASTE
                                            corrección)               la pena vs. reframe   DECISION
                                                                      "specificity"         (ver abajo)
  4. Alternatives sufficiently explored?    SÍ (A/B/C + reframing    Propone una 4ta       CONFIRMED,
                                            de C)                     opción (specificity)  con adición
  5. Competitive/market risks covered?     N/A (interno)             Riesgo de validez del CONFIRMED
                                                                      ejercicio si el mapa
                                                                      se muestra/oculta mal
  6. 6-month trajectory sound?             Sí, tras las correcciones Escenario de          CONFIRMED
                                            de 0A                     "re-peso silencioso"  (tras corregir)
                                                                      + rubric drift
═══════════════════════════════════════════════════════════════════════════
CONFIRMED = 5/6 tras incorporar las correcciones. [subagent-only] — sin Codex disponible.
```

**Nota sobre el punto 2/3 (no auto-decidido, va al gate como matiz, no como bloqueo):** la voz
independiente propuso una alternativa más profunda — puntuar la **especificidad** de cualquier ubicación
que el trainee dé (¿fue una calle+cruce accionable, sin importar si coincide con un valor pre-configurado
específico?) en vez de matching contra un valor exacto. Es una idea real y más transferible al mundo real
(entrena la habilidad general, no la memoria de una dirección ficticia específica), pero es un cambio de
qué se mide, no un defecto de este plan — y **una vez corregida la premisa 1** (el trainee sí recibe la
ubicación configurada antes de la llamada), medir contra el valor específico configurado vuelve a ser
válido y es lo que el usuario pidió literalmente ("evaluar... qué tan efectiva fue" respecto a LA
ubicación del escenario, no a cualquier ubicación plausible). No se auto-decide un cambio de qué se mide
sin que el usuario lo pida — se documenta como alternativa futura en TODOS.md (cherry-pick #11 relacionado)
y se cita en el gate para que el usuario la vea, sin bloquear Approach A.

---

## Section 1 — Architecture Review

**Componentes nuevos y su relación con lo existente:**

```
                    ┌───────────────────────────────────────────┐
                    │  frontend: ScenarioEditorPage.tsx           │  (MODIFICADO)
                    │  sección nueva "Ubicación del incidente"    │
                    │  usa <LocationMiniMap mode="author">        │
                    └──────────────────┬────────────────────────┘
                                       │ PUT/POST /scenarios/{id}/location
                                       ▼
                    ┌───────────────────────────────────────────┐
                    │  server/app.py — endpoints CRUD nuevos      │  (MODIFICADO)
                    │  ScenarioLocationIn/Out (autoría, con hints)│
                    │  ScenarioLocationAccessOut (trainee, SIN    │
                    │  hints, CON street/cross_street/landmark)   │
                    └──────────────────┬────────────────────────┘
                                       │
                    ┌──────────────────▼────────────────────────┐
                    │  persistence/sqlite_scenario_location_store │  (NUEVO)
                    │  tabla nueva `scenario_locations`, 1:1 PK   │
                    │  scenario_id — mismo patrón que video       │
                    └──────────────────┬────────────────────────┘
                                       │ lectura en call.start
       ┌───────────────────────────────┼────────────────────────────────┐
       ▼                               ▼                                 ▼
frontend: CallPage.tsx          core/scoring.py::score_session    frontend: SessionBreakdown.tsx
secuencia (orden final,           (MODIFICADO — un              (MODIFICADO)
Fase 2 Pass 7): location          LocationGroundTruthPoint        <LocationMiniMap mode="review">
briefing → video gate (si         combinado se agrega a           + narrativa de claridad de ubicación
existe) → call.start. Location   all_points, línea 109;           + evaluation.location_detail
briefing inserta                 _location_narrative() nuevo      (nuevo, solo-reporte — ver Fase 2 F1)
<PreCallLocationBriefing> +       genera texto para
opt-in <InCallLocationPanel>      strengths/improvements)
(nuevo, patrón InCallVideoPanel.tsx,
cerrado por default) visible
durante la llamada
```

**Data flow — nuevo path (`location briefing → call → scoring`):**
```
  CONFIG (autor) ──▶ PERSISTENCIA ──▶ PRE-LLAMADA (trainee) ──▶ TRANSCRIPT ──▶ SCORING ──▶ REVIEW
       │                  │                  │                     │              │            │
       ▼                  ▼                  ▼                     ▼              ▼            ▼
  [campos vacíos?    [tabla no existe   [sin ubicación         [ubicación   [sin ubicación   [sin datos:
   → sin ubicación    para este          configurada →          mencionada   configurada →    ocultar
   configurada,       scenario_id →      call.start directo,    tarde/nunca] omitir punto de   subsección,
   omitir sección]    tratar como        sin gate nuevo,                     all_points,       no mostrar
                       "sin ubicación"]  cero cambio vs. hoy]                narrativa N/A]     0/null]
```
Los 4 shadow paths (sin config, tabla ausente, no mencionado, sesión histórica sin datos) degradan al
mismo comportamiento de hoy — nunca bloquean `finish_call()` ni `call.start`.

**Coupling — antes/después:** `core/scoring.py` sigue siendo una función pura, síncrona, determinista —
sin llamadas de red nuevas (a diferencia de `motor-de-metricas.md`, este plan no introduce dependencia de
LLM). `CallPage.tsx` gana un gate secuencial más (mismo patrón que video), no un estado nuevo en
`TurnStateMachine`.

**Scaling:** cero llamadas nuevas por sesión — el gate de pre-llamada es una lectura de datos ya
cargados junto con el escenario, no una llamada adicional. No introduce ningún multiplicador nuevo.

**Puntos únicos de falla:** ninguno nuevo — igual que video, si `scenario_locations` no tiene fila para
un `scenario_id`, el sistema se comporta exactamente como hoy (sin ubicación configurada).

**Postura de rollback:** aditivo puro — tabla nueva + campos opcionales en `evaluation`. `git revert`
limpio; `DROP TABLE` opcional. Riesgo de rollback: **bajo**.

## Section 2 — Error & Rescue Map

```
  METHOD/CODEPATH                          | WHAT CAN GO WRONG                        | EXCEPTION CLASS
  ------------------------------------------|-------------------------------------------|------------------
  sqlite_scenario_location_store.get()      | Fila no existe para scenario_id           | (debe devolver
  (NUEVO)                                   |                                            | None, no raise)
  PreCallLocationBriefing (NUEVO)           | location es None (no configurada)          | (debe omitir el
                                            |                                            | gate, seguir directo
                                            |                                            | a call.start, igual
                                            |                                            | que hoy sin video)
  score_session — fusión de location a      | ScenarioLocation con todos los campos      | (debe omitir el
  all_points (MODIFICADO)                   | vacíos (autor guardó la sección sin        | punto, no generar
                                            | llenar nada)                               | uno vacío que
                                            |                                            | siempre falla)
  _location_narrative() (NUEVO)             | transcript vacío o sin turnos de operador  | (debe devolver
                                            |                                            | narrativa N/A, no
                                            |                                            | raise)
  sqlite_scenario_location_store (NUEVO)    | Escritura durante lock compartido de       | sqlite3.OperationalError
                                            | SQLite (topología compartida, TODO-20)     |
  ------------------------------------------|-------------------------------------------|------------------

  EXCEPTION CLASS                    | RESCUED? | RESCUE ACTION                          | USER SEES
  ------------------------------------|----------|------------------------------------------|------------------
  Fila ausente / ubicación no         | Y        | tratar como "sin ubicación configurada" — | Sin sección de
  configurada                         |          | mismo camino en autoría, pre-llamada y    | ubicación en
                                     |          | scoring                                    | ningún lado —
                                     |          |                                            | comportamiento
                                     |          |                                            | idéntico a hoy
  Campos todos vacíos                 | Y (NUEVO)| omitir el punto de all_points, no          | sin cambio en el
                                     |          | generar un punto que siempre falla         | score
  sqlite lock                         | Y        | reintento con backoff — mismo patrón ya    | transparente si
                                     | (mismo   | usado para la topología compartida         | el retry tiene
                                     | patrón)  | (TODO-20)                                  | éxito
```

**Gap crítico identificado:** ninguno nuevo de la clase "breaking change" (a diferencia de
`motor-de-metricas.md`, que sí necesita migrar el contrato de `SpeechToTextPort`) — este plan es
puramente aditivo: nueva tabla, nuevos campos opcionales, nuevo componente de UI condicional. El único
riesgo real es el ya nombrado en 0A punto 6: la migración manual de los 3 escenarios semilla en
producción no ocurre sola.

## Section 3 — Security & Threat Model

**Expansión de superficie de ataque:** un endpoint CRUD nuevo (`/scenarios/{id}/location`), mismo patrón
de autenticación por bearer token que el resto de `/scenarios/*` — sin superficie nueva de clase distinta.

**Autorización:** sin cambios respecto al patrón existente — mismo self-scoping por `supervisor_id` en
`history.*`; el propio recurso `/scenarios/*` ya es de acceso uniforme para cualquier sesión autenticada
(`TODO-16`, PENDING, pre-existente, no agravado por este plan — ver 0A punto 7).

**Validación de input:** sin llamadas LLM (a diferencia de `motor-de-metricas.md`) — no hay superficie de
prompt injection en este plan. `street`/`cross_street`/`landmark`/`additional_directions` son texto libre
de autoría (mismo nivel de confianza que `briefing`/`match_hints` hoy) — nunca se re-inyectan a un prompt.

**Clasificación de datos:** ubicaciones ficticias de escenario, sin PII ni proxy de característica
protegida (a diferencia del hallazgo de "acento" en `motor-de-metricas.md`) — clasificación de riesgo
baja.

**Secretos y credenciales:** ninguno nuevo.

## Section 4 — Data Flow & Interaction Edge Cases

```
  INTERACCIÓN                    | EDGE CASE                          | HANDLED? | CÓMO
  --------------------------------|-------------------------------------|----------|-----------------------
  PreCallLocationBriefing         | Escenario sin ubicación configurada| SÍ (debe)| gate se omite, flujo
                                  |                                      |          | idéntico a hoy
  PreCallLocationBriefing +       | Escenario con video Y ubicación    | SÍ (debe)| secuencia: location
  PreCallVideoGate                | configurados                        |          | briefing → video gate →
                                  |                                      |          | call.start (Fase 2 Pass 7,
                                  |                                      |          | F14/F15 — orden final,
                                  |                                      |          | corrige contradicción
                                  |                                      |          | previa entre fases)
  SessionBreakdown — mini-mapa    | Sesión histórica sin datos de       | SÍ (debe)| ocultar subsección,
  de revisión                     | ubicación (pre-feature)             |          | nunca mostrar mapa vacío
  ScenarioEditorPage — sección    | Autor llena solo 1 de 4 campos      | SÍ (debe)| punto combinado usa
  de ubicación                    | (ej. solo street)                   |          | solo los campos no
                                  |                                      |          | vacíos como hints
```

## Section 5 — Code Quality Review

1. **DRY:** `LocationMiniMap.tsx` con un solo componente parametrizado por `mode: 'author'|'brief'|'review'`
   en vez de 3 componentes separados — evita triplicar el SVG del mapa.
2. **Naming:** `label` del punto generado = el valor real configurado (ej. `"5th Avenue"`), nunca un
   nombre de campo genérico — ver 0A punto 5, evita el fallback de `_matches_point` como detector de
   palabras sueltas.
3. **Over-engineering check:** no se justifica un modelo de geometría vectorial (líneas, múltiples
   marcadores) para un solo flag esquemático — ver Approach B, rechazada.
4. **Under-engineering check:** un punto de ubicación con todos los campos vacíos NO debe generarse como
   un `LocationGroundTruthPoint` vacío que automáticamente cuenta como "missing" — debe omitirse de
   `all_points` por completo (Sección 2).
5. **Complejidad ciclomática:** extraer `_location_ground_truth_point()` y `_location_narrative()` como
   funciones privadas separadas en `scoring.py`, siguiendo el patrón ya usado (`_completeness`,
   `_clarity`, etc. son funciones privadas separadas) — no inflar `score_session` directamente.

## Section 6 — Test Review

```
  NEW UX FLOWS:
    - Ver la pantalla de pre-llamada de ubicación (mapa + calle/cruce/referencia + briefing) antes de
      call.start, para escenarios con ubicación configurada
    - Secuencia de dos gates (video + ubicación) cuando ambos están configurados
    - Ver el mini-mapa en modo solo-lectura en SessionBreakdown tras terminar la llamada
    - Autorar la sección de ubicación en ScenarioEditorPage (click-to-place del flag)

  NEW DATA FLOWS:
    - ScenarioLocation (autoría) → SQLite tabla nueva → ScenarioLocationAccessOut (trainee, sin hints)
    - ubicación configurada → LocationGroundTruthPoint combinado → all_points → completeness/
      time_to_critical_data (sin categoría ponderada nueva)
    - evaluation dict extendido → SQLite evaluation_json (mismo boundary) + narrativa en
      strengths/improvements + `evaluation.location_detail` (NUEVO, solo-reporte — ver Fase 2 hallazgo
      F1: `{street: 'collected'|'missing'|'n/a', cross_street: ..., landmark: ..., first_mention_seconds:
      number|null}`, nunca entra a `category_scores`, existe solo para que `SessionBreakdown` pinte el
      desglose por campo sin inventar un schema no revisado)

  REGRESSION (explícita):
    - TODO-17: con el canal de entrega nuevo, ¿un trainee que recibe la ubicación configurada deja de
      "inventar" datos como el "Westfield Shopping Center" del reporte real documentado? (test con
      transcript sintético que menciona la calle real configurada — debe puntuar collected, no missing)
```

Ningún edge case queda sin plan de manejo explícito. Test plan artifact detallado: ver "Implementation
Tasks" en la Sección de Eng (Fase 3) más abajo — se omite un archivo separado en disco dado que `jq` no
está instalado y el alcance cabe íntegro en este documento.

## Required Outputs — Fase 1 (CEO)

### "NOT in scope"
1. **Editor de mapa interactivo con líneas dibujadas / múltiples marcadores** (Approach B, cherry-pick
   #7) — sobre-construcción sin pedido explícito.
2. **Mostrar el mapa/calles al trainee automáticamente durante la llamada en vivo, sin acción del
   trainee.** El acceso opt-in (cerrado por default, un botón para reabrirlo) SÍ está en alcance —
   cherry-pick #8, corregido en Fase 2 (hallazgo F12) — solo el auto-display sin interacción queda fuera.
3. **Reframing a "scoring de especificidad" en vez de matching contra el valor configurado** (nota bajo
   la consensus table) — válido como dirección futura, no se auto-adopta sin pedido explícito del
   usuario.
4. **`rubric_version` formal / soporte multi-marcador** (cherry-picks #10, #11) — diferidos a TODOS.md.

### "What already exists"
Ver 0B — `CriticalDataPoint`/`_matches_point`/`_time_to_critical_data`, patrón de tabla 1:1 sin
`ALTER TABLE`, `PreCallVideoGate.tsx`, split autoría/trainee de video, render genérico de
`SessionBreakdown.tsx`. Ninguno se reconstruye.

### TODOS.md updates (candidatos a TODO-21+)
1. **Qué:** migrar manualmente los 3 escenarios semilla en producción (retirar el `CriticalDataPoint`
   suelto de ubicación al adoptar `ScenarioLocation`). **Por qué:** `_seed_scenarios()` es un no-op contra
   una DB ya poblada (0A punto 6). **Effort:** S (manual, vía editor). **Priority:** P1 — antes de shipear,
   o se duplica el conteo del mismo hecho. **Decisión:** Add to TODOS.md, bloqueante para el rollout, no
   para el código.
2. **Qué:** soporte de múltiples marcadores por escenario (incidente + ruta de escape, testigos).
   **Por qué:** cherry-pick #10, fuera del pedido singular original. **Effort:** M. **Priority:** P3.
3. **Qué:** `rubric_version` formal en `evaluation` para versionar cambios de denominador de completeness
   a través del tiempo (afecta a esta feature y a la de video ya shippeada). **Por qué:** cherry-pick #11,
   cross-cutting, no exclusivo de este plan. **Effort:** M. **Priority:** P2.
4. **Qué:** cuando `motor-de-metricas.md` (APPROVED) se implemente, incluir el punto de ubicación en el
   conjunto de hechos evaluados por el juez LLM, en vez de dejarlo solo en el matcher de hints.
   **Por qué:** 0A punto 3 — coordinación entre planes hermanos. **Effort:** XS (una vez el juez exista).
   **Priority:** P2, atado a la implementación de T1-T16 de ese plan.

### Completion Summary — Fase 1 (CEO)
```
  +====================================================================+
  |            CEO PLAN REVIEW — COMPLETION SUMMARY (Fase 1)            |
  +====================================================================+
  | Modo                  | SELECTIVE EXPANSION                        |
  | Premisas challenged   | 8 (3 CRÍTICO, 2 corregidas tras subagente) |
  | 0C-bis alternativas   | 3 (A recomendada, tras corrección de C)    |
  | Cherry-picks (0D)     | 11 — 6 ACEPTADO, 1 TASTE DECISION,         |
  |                       | 2 RECHAZADO/NOT-in-scope, 2 DEFERIDO       |
  | Dual voices           | [subagent-only] — Codex no instalado       |
  | Consensus             | 5/6 CONFIRMED (tras incorporar correcciones)|
  | NOT in scope          | escrito (4 items)                          |
  | What already existe   | escrito (0B)                                |
  | TODOS.md updates      | 4 items propuestos                          |
  | Corrección mayor      | SÍ — premisa 1 invertida en el borrador     |
  |                       | inicial, corregida tras la voz independiente|
  +====================================================================+
```

**PHASE 1 COMPLETE.** Codex: no disponible. Claude subagent: 1 hallazgo crítico que invirtió la
recomendación central del borrador (premisa del canal de entrega), más 3 correcciones de hecho.
Consensus: 5/6 confirmado tras incorporar las correcciones — el desacuerdo restante (punto 2/3, reframing
a "specificity") se documenta como nota, no como bloqueo, y se surface en el gate.
Passing to Phase 2 (Design Review — UI scope detectado: mini-mapa, formulario del editor, pantalla de
pre-llamada, dashboard).

---

# Fase 2 — Design Review

**Nota de corrección (léase antes que el resto de esta fase):** el borrador inicial de esta fase (antes
de la voz de diseño independiente) se auto-calificó 8/10 con "0 decisiones diferidas." Ambas afirmaciones
eran falsas. La voz independiente encontró: (1) el mapa de revisión pedía datos que el scoring de Fase 1
nunca produce; (2) "calles como texto, no geometría" + un flag sin nada respecto a qué posicionarlo hace
que el mapa no represente nada — el hallazgo de diseño más importante de todo el documento; (3) el
rechazo de acceso en vivo (cherry-pick #8) usaba un argumento que el propio usuario ya revirtió para
video (`InCallVideoPanel.tsx` ya existe); (4) contradicción de orden de gates entre Fase 1 y Fase 2; (5)
todo el copy de UI estaba en español, cuando el 100% de la UI existente de este repo está en inglés
(comentarios y docs en español, strings de usuario en inglés); (6) overflow real en `.call-card` con el
contenido especificado; (7) la auditoría de Pass 5 citó 2 de los 21 design tokens reales. Las
correcciones ya están incorporadas en Fase 1 (cherry-pick #8, orden de gates, diagrama de Sección 1) y se
incorporan a continuación en cada pass afectada — el texto original y el porqué del cambio se conservan
donde es útil para el lector.

No existe `DESIGN.md` (gap ya documentado como TODO pendiente en la revisión de video anterior — "correr
`/design-consultation`" — no se repite el hallazgo, se referencia). Se calibra contra el vocabulario de
facto ya en uso: `--bg:#061321`, `--muted:#8fa5ba` (`frontend/src/styles/globals.css`), componentes
`ScoreRing`, `.scorebar`/`.progress`, `.panel`/`.functional-review-grid` (todos ya identificados en la
revisión de `motor-de-metricas.md`). `DESIGN_NOT_AVAILABLE` verificado de nuevo en esta sesión (`design
setup` pide una API key de OpenAI, no configurada) — se usan wireframes ASCII en vez de mockups
generados, igual que la revisión anterior.

## Step 0 — Design Scope Assessment

**0A. Rating inicial:** **4/10.** El plan de Fase 1 especifica el comportamiento funcional de 3
pantallas nuevas (sección de autoría, pantalla de pre-llamada, review post-llamada) pero cero
especificidad visual: sin jerarquía de información diagramada, sin tabla de estados, sin arco emocional
del trainee, sin verificación contra el vocabulario visual existente. Un 10/10 tendría las tres pantallas
diagramadas, cada estado de interacción cubierto, y el mini-mapa especificado a nivel de trazo (no "un
SVG con un flag").

**0B. DESIGN.md:** no existe — se usan los Principios de Diseño universales + el vocabulario de facto.

**0C. Leverage existente:** `ScoreRing`, `.panel`, `.functional-review-grid`, patrón `AreaChart` de
recharts, paleta `--bg`/`--muted`, y el patrón de `PreCallVideoGate.tsx` (gate de pantalla completa,
botón único de confirmación) — todos reutilizables sin inventar vocabulario nuevo.

**0D. Focus areas:** las 7 dimensiones (auto-decidido, P1 completeness).

## Design Dual Voices

CODEX SAYS (design — UX challenge): *(no disponible)*.

CLAUDE SUBAGENT (design — independent review): ver hallazgos incorporados en las pasadas 1-7 debajo —
resumen y scorecard al final de esta fase.

## Pass 1 — Information Architecture (4/10 → 8/10, corregido tras voz independiente)

**Hallazgo F17 [CRÍTICO, el más importante de esta fase]: "calles como texto, no geometría" + un flag
sin nada respecto a qué posicionarlo no representa nada.** El borrador inicial aceptaba en 0C-bis que las
calles son texto plano, no geometría dibujada — pero entonces un flag colocado en `marker_x/marker_y` no
tiene ningún punto de referencia visual: es un pin flotando en un lienzo vacío con 4 marcas de compás. Eso
no es "un mini-mapa," es una decoración (Pass 4 blacklist #6, aplicado contra el propio feature). El
pedido del usuario — "un mini mapa con un flag... nombres de calles, avenidas" — necesita que el flag
tenga sentido posicional. **Corrección de diseño (adoptada):** el lienzo dibuja `street` como una línea
horizontal con su nombre a lo largo, `cross_street` como una línea vertical con el suyo; su intersección
es el punto de referencia; el flag se posiciona con un offset respecto a esa intersección (`marker_x/y`
ahora sí significan algo: "esquina noreste de 5th Ave y Main St"); `landmark`, si está configurado, es un
cuadrado pequeño con su etiqueta. 3 primitivas SVG, cumple el pedido literalmente, y le da a `review` algo
real para resaltar (ver Pass 1 sección review, abajo).

**Jerarquía correcta para las 3 pantallas nuevas (todo el copy en inglés — ver Pass 4/hallazgo F19: el
100% de la UI existente de este repo está en inglés):**

```
  ScenarioEditorPage.tsx — "Incident location (optional)" (autoría)
  ┌──────────────────────────────────────────────────────────┐
  │ 1º  Street / Cross street / Landmark (3 inputs, texto      │
  │     PRIMERO — no se puede posicionar un flag con sentido    │
  │     antes de que exista una calle que dibujar, hallazgo F3) │
  │ 2º  <LocationMiniMap mode="author">, deshabilitado hasta    │
  │     que "Street" tenga texto — copy: "Enter a street name  │
  │     to place the marker on the map"                        │
  │ 3º  Zone/city + Additional directions (colapsable, "More    │
  │     details" — no compiten con los 3 campos core)           │
  │ 4º  "Remove location" (mismo patrón que "Remove video")     │
  └──────────────────────────────────────────────────────────┘
  Sección completa gateada por isEditing (mismo patrón que video, F9) — con copy de empty-state
  explicando por qué: "Save the scenario first, then add a location."

  PreCallLocationBriefing.tsx (pre-llamada, pantalla completa,
  mismo patrón que PreCallVideoGate — copy en inglés, F19)
  ┌──────────────────────────────────────────────────────────┐
  │ 1º  <LocationMiniMap mode="brief"> — mapa con geometría     │
  │     (F17), flag ya puesto, SIN hints                        │
  │ 2º  Street / Cross street / Landmark como texto (lo que el │
  │     trainee debe poder repetir)                             │
  │ 3º  Briefing completo, en un bloque con `max-height` +      │
  │     overflow-y:auto (F4 — sin esto, desborda `.call-card`)  │
  │ 4º  Botón — label condicional (F14): "Continue" si sigue    │
  │     un video gate, "Start Call" si es el último paso        │
  └──────────────────────────────────────────────────────────┘

  CallPage.tsx durante la llamada (NUEVO — cherry-pick #8 corregido, F12)
  ┌──────────────────────────────────────────────────────────┐
  │ <InCallLocationPanel> cerrado por default, botón opt-in     │
  │ "Check the address again" — mismo patrón que                │
  │ InCallVideoPanel.tsx ("Watch video again")                  │
  └──────────────────────────────────────────────────────────┘

  SessionBreakdown.tsx — subsección "Location" (review)
  ┌──────────────────────────────────────────────────────────┐
  │ 1º  Bloque anidado en el panel "Information Collected"      │
  │     existente (no un panel nuevo, F2): check-line ok/bad     │
  │     por street/cross_street/landmark, usando                │
  │     evaluation.location_detail (NUEVO, solo-reporte, F1)     │
  │ 2º  <LocationMiniMap mode="review"> — SÍ aporta información   │
  │     nueva ahora que dibuja geometría (F17): resalta en        │
  │     verde la calle/cruce mencionados, gris los que no          │
  │ 3º  Narrativa de claridad ("Gave the street at 0:12, but      │
  │     never mentioned a cross street or landmark.")             │
  └──────────────────────────────────────────────────────────┘
```

**Constraint worship:** en la pantalla de pre-llamada, las 3 cosas que importan son: el mapa con
geometría real, las 3 frases de ubicación, y el botón — el briefing narrativo completo es secundario,
colapsable/truncado (F4), y nunca compite por atención con lo que el trainee debe memorizar.

## Pass 2 — Interaction State Coverage (2/10 → 8/10, corregido tras voz independiente)

**Hallazgo F7 [HIGH]: el borrador original inventó primitivos de UI que no existen en este repo.**
`grep -rn "toast|skeleton" frontend/src` → cero resultados. Los primitivos reales, ya en uso: loading =
texto plano `.empty-copy` (`CallPage.tsx:89`, `"Preparing your session…"`) o swap del label del botón
("Saving…", `ScenarioEditorPage.tsx:269,296`); error = notificación inline `.call-notice.error`
(`globals.css:135`, ya usada en `.scenario-editor-error`). Se corrige la tabla completa para usar solo
estos.

**Hallazgo F6 [CRÍTICO]: el error de carga, tal como estaba especificado, reintroduce la injusticia de
TODO-17 que este plan existe para arreglar.** Si la pantalla de pre-llamada falla al cargar y el trainee
arranca la llamada sin haber visto la ubicación, el scoring seguía fusionando el punto de ubicación a
`all_points` de todos modos — el trainee sería marcado "Missing: 5th Avenue" por una falla técnica, no
por su comunicación. **Corrección:** el fallo de carga (o "Skip" explícito) marca `location_delivered:
false` en la sesión; `score_session` **omite** el punto de ubicación de `all_points` cuando eso ocurre, y
`SessionBreakdown` muestra "Location wasn't shown to the trainee (technical issue) — not scored" en vez
de contar como falta. También se agrega la misma vía de escape que ya tiene video ("Skip, start call") —
un reintento sin salida es peor que el precedente de video.

```
  FEATURE                  | LOADING              | EMPTY                       | ERROR                       | SUCCESS                       | PARTIAL
  --------------------------|----------------------|-----------------------------|-------------------------------|--------------------------------|------------------------------
  ScenarioEditorPage        | ".empty-copy" texto   | "No location set — add a   | ".call-notice.error" inline, | flag posicionado en el mapa   | 1-2 de 3 campos core
  sección Location          | plano ("Loading…")    | street name to place it on | "Couldn't save location.     | + campos con valor;           | llenos → esos entran a
                            |                       | the map." — mapa            | Try again." + botón           | validación: marcador sin       | all_points, los vacíos se
                            |                       | deshabilitado hasta que     | reintentar                    | ningún campo de texto no       | omiten (nunca "N/A")
                            |                       | "Street" tenga texto (F8)   |                                | pasa la validación de guardado |
  PreCallLocationBriefing   | ".empty-copy" texto   | escenario sin location      | ".call-notice.error" +        | mapa + calle/cruce/referencia | 1 campo vacío → esa línea
                            | plano (mismo patrón   | configurada (según F8: 0    | "Retry" + "Skip, start call"  | + botón habilitado             | se omite del texto, el mapa
                            | que "Preparing your   | de street/cross/landmark) → | (mismo escape que video, no   |                                 | dibuja solo lo configurado
                            | session…")            | gate se omite, sin cambio   | bloqueo indefinido) — falla   |                                 |
                            |                       | de comportamiento vs hoy    | marca location_delivered:     |                                 |
                            |                       |                             | false (F6) → excluido del     |                                 |
                            |                       |                             | scoring, nunca penaliza       |                                 |
  InCallLocationPanel       | —  (datos ya          | —  (solo existe si hubo     | —  (datos ya en memoria del   | panel abierto muestra el       | —
  (NUEVO)                   | cargados antes de     | briefing pre-llamada)       | cliente, sin red)              | mismo contenido de brief       |
                            | la llamada)           |                             |                                | mode                           |
  SessionBreakdown          | ".empty-copy" texto   | sesión histórica sin        | — (dato ya persistido, sin    | check-lines ok/bad por campo   | location_delivered:false
  subsección Location       | plano                 | evaluation.location_detail  | fallo posible en lectura)     | + mapa con overlay verde/gris  | → narrativa explícita "not
                            |                       | → ocultar subsección        |                                | + narrativa                    | scored (technical issue)",
                            |                       | completa                    |                                |                                 | nunca "0% clarity"
```

## Pass 3 — User Journey & Emotional Arc (5/10 → 8/10, corregido tras voz independiente)

**Hallazgo F13 [CRÍTICO]: "la ansiedad es parte del ejercicio" no es una decisión de diseño, es una
deferral disfrazada — y contradice la pedagogía ya establecida por la feature hermana.** El video ya
resolvió este mismo dilema con la respuesta contraria en cada punto: sin auto-advance, controles nativos
para rebobinar ("es práctica, no examen"), un beat "Take a moment." antes de empezar, una vía de escape
("Skip"), y acceso en vivo opcional (`InCallVideoPanel`). `GOALS.md` objetivo 4 ("Confianza del espacio de
práctica") es un objetivo de producto declarado, no solo de video. Aceptar la ansiedad como "parte del
ejercicio" convierte silenciosamente el feature de "medir claridad de comunicación" (lo que pidió el
usuario) en "medir memoria de 90 segundos" — el mismo reframing hacia "specificity" que la Fase 1 ya
había decidido NO auto-adoptar sin pedido explícito. **Corrección: se adopta la misma pedagogía que
video, verbatim** (acceso en vivo opcional vía `InCallLocationPanel`, sin timer, sin framing de examen).

```
  PASO | EL TRAINEE HACE                          | SIENTE                        | ¿EL PLAN LO CUBRE?
  -----|--------------------------------------------|--------------------------------|---------------------
  1    | Abre el escenario, ve la pantalla de        | Preparado — tiene un mapa      | SÍ (Pass 1) — mapa +
       | pre-llamada                                 | concreto, no un párrafo a      | texto en jerarquía
       |                                              | memorizar en abstracto         | correcta
  2    | Empieza la llamada                          | Neutral/en control — si olvida | SÍ (corregido, F12/F13)
       |                                              | un detalle, sabe que puede     | — InCallLocationPanel
       |                                              | reabrir el mapa (opt-in)       | opt-in, mismo patrón
       |                                              |                                | que video
  3    | Da la ubicación al dispatcher-IA            | Confianza, no examen — el      | SÍ, tras la corrección
       |                                              | acceso opcional en vivo quita  | de F13 — se elimina el
       |                                              | la presión de memoria pura     | framing "es un test de
       |                                              |                                | memoria"
  4    | Termina la llamada, ve el review             | Vulnerable — es la primera vez| SÍ (0A punto 8,
       |                                              | que ve retroalimentación sobre| GOALS.md) — narrativa
       |                                              | algo que sí sabía             | de coaching, no de
       |                                              |                                | juicio
  5    | Ve el desglose por campo + el mapa con        | Claridad accionable — sabe    | SÍ (Pass 1, mode=review,
       | overlay verde/gris                            | EXACTAMENTE qué faltó, y el   | tras F17)
       |                                              | mapa ahora sí muestra por qué  |
```

**Time-horizon:** 5 segundos (la pantalla de pre-llamada comunica "esto es lo que necesitas saber"
instantáneamente — mapa con geometría real + 3 líneas, no un párrafo); 5 minutos (durante la llamada, el
trainee tiene una salida si se traba — `InCallLocationPanel`, no presión sin salida); 5 años/repetición
(con la práctica, dar ubicaciones completas se vuelve automático — el review refuerza el patrón con
coaching, no con juicio).

## Pass 4 — AI Slop Risk (App UI) (7/10 → 9/10)

Clasificación: **App UI** (dashboard/herramienta de trabajo, no marketing) — aplican las App UI Rules +
Universal Rules.

**Hallazgo [HARD REJECTION evitado, pero cerca]:** la palabra literal del pedido del usuario es "flag" —
el riesgo real es implementarlo como el emoji 🚩 o un pin de mapa genérico estilo Google Maps (gota roja
con sombra) — ambos son un patrón de slop reconocible (blacklist #7, emoji como elemento de diseño; y un
pin tipo Google Maps contradice directamente "no se necesita un motor de geolocalización como el de
Google"). **Fix:** el marcador es un ícono de línea fina (`stroke`, sin relleno, sin sombra), mismo
grosor de trazo ya establecido en la app (`1.7`, ver Pass 5/F16).

**Rosa de los vientos:** el riesgo de slop es una ilustración de brújula decorativa/skeuomórfica —
agravado por el hallazgo F17 (Pass 1): sobre un lienzo sin geografía, la rosa de los vientos es pura
decoración (blacklist #6). **Fix, ya incorporado en Pass 1:** una vez que el lienzo dibuja
calle/cruce/referencia como geometría real (F17), la rosa de los vientos (4 marcas de línea fina, "N" en
texto) deja de ser decorativa — orienta geometría real, igual que en un plano de arquitecto.

**Hallazgo F19 [HIGH, corrección de idioma]:** el borrador inicial de esta fase escribió todo el copy de
UI en español ("Sin ubicación configurada", "Empezar llamada", etc.). `grep` sobre componentes existentes
confirma que el 100% del copy de usuario en este repo está en inglés ("Critical data points", "Before
you call it in", "Take a moment.") — solo comentarios de código y documentos de diseño están en español.
Un implementador siguiendo el spec literal habría shippeado una isla de español dentro de una app en
inglés. **Corregido en todas las pasadas de arriba y abajo** — todo el copy citado en este documento a
partir de aquí está en inglés.

**Sin card-grid, sin gradientes decorativos, sin iconos en círculos de color** — el mini-mapa es un solo
lienzo funcional, no una colección de tarjetas; no hay riesgo de los patrones #1-3 del blacklist.

## Pass 5 — Design System Alignment (3/10 → 8/10, corregido tras voz independiente)

**Hallazgo [MEDIUM, proceso]:** el borrador inicial de esta pasada citó 2 de los 21 design tokens reales
de `globals.css` (`--bg`, `--muted`) y se auto-calificó 7/10 — una auditoría que cubre el 10% del sistema
no es una auditoría, es un resumen. Se corrige con la paleta completa verificada:

```
  ELEMENTO                  | TOKEN/VALOR                          | PRECEDENTE
  ---------------------------|----------------------------------------|---------------------------------
  Fondo del lienzo           | var(--bg-deep)  (#04101c)             | .call-card usa el mismo tono
  Borde del lienzo           | 1px solid var(--border)  (#183650)    | .video-gate-player:147
  Radio del lienzo           | 12px (NO var(--radius):16px — ese es  | .panel exterior ya usa 16px;
                              | para el .panel exterior)               | el lienzo interno usa menos
  Líneas de calle (F17)      | stroke: var(--track)  (#17304a),      | color de "vía"/track ya
                              | stroke-width: 2                        | existente en el sistema
  Etiquetas de calle          | fill: var(--muted)  (#8fa5ba), 11-12px | mismo tamaño que .check-line
  Marcador/flag               | stroke: var(--danger)  (#e44b55),     | mismo peso de ícono que
                              | stroke-width: 1.7, sin fill, sin sombra| Logo.tsx / CallPage.tsx / gate
  Rosa de los vientos          | stroke: var(--muted-2)  (#6f879f),   | tono secundario ya en uso
                              | stroke-width: 1, "N" en var(--muted)   |
  Overlay review (F17)        | ok: var(--success) #41c979 / bad:     | mismo trío que .check-line
                              | var(--danger) #e44b55 / n-a:          | .ok/.bad/.warn
                              | var(--muted-2)                        |
  Mecánica SVG                | viewBox + stroke="currentColor"       | único precedente SVG a mano
                              |                                        | (HomePage.tsx)
```

**Componente nuevo (`LocationMiniMap`) — ¿encaja en el vocabulario existente?** Sí, como contenido SVG
propio dentro de `.panel` (mismo criterio que los charts de `recharts`, que heredan `--bg`/`--muted` en
vez de traer paleta propia) — con la tabla de arriba, no hay ningún color/valor nuevo inventado fuera del
sistema.

## Pass 6 — Responsive & Accessibility (6/10 → 8/10)

**Responsive:** la app ya tiene un piso mínimo intencional de `min-width:1180px` (decisión preexistente,
no se agrega soporte por debajo de eso, mismo precedente que la revisión de video). El mini-mapa a
240×240px cabe sin cambios de layout en ese piso.

**Accesibilidad — hallazgo real, no cosmético:** un mapa de "clic para posicionar el flag" es
**inaccesible por teclado y para lectores de pantalla por diseño**, si es la única forma de posicionarlo.

**Corrección (hallazgo F18, invierte la solución original):** inputs numéricos crudos de `marker_x`/
`marker_y` (0-100%) no son accesibilidad, son filtrar el modelo de datos a la UI — pedirle a un autor que
escriba "62 / 38" no es mejor que el mouse, y encima el borrador original lo marcaba **P1 bloqueante**
para un valor que, tal como estaba diseñado antes de F17, no afectaba ningún score. **Fix correcto:** el
lienzo es un único elemento enfocable (`tabIndex=0`, `role="application"`) con nudge por flechas de
teclado (2% por pulsación, 10% con Shift) y `aria-live` que anuncia la posición resultante **en palabras
derivadas de la geometría de F17** ("north-east of 5th Ave and Main St"), no en coordenadas. `role="img"`
+ `aria-label` describiendo calle/cruce/referencia en texto para que un lector de pantalla no vea el mapa
como una imagen opaca. La app ya tiene un estilo de foco global (`:focus-visible { outline: 2px solid
var(--primary) }`, `globals.css:32`) — el lienzo lo hereda sin CSS nuevo.

**Contraste:** las etiquetas de calle sobre el lienzo deben cumplir el mismo mínimo 4.5:1 ya pendiente de
verificar para `--muted` sobre `--bg` (TODO ya anotado en la revisión de video, T7 relacionado) — no se
duplica el TODO, se referencia.

## Pass 7 — Unresolved Design Decisions

**Nota de corrección:** el borrador inicial reportó "3 resueltas, 0 diferidas" en esta pasada. La voz
independiente contó al menos 9 decisiones que producen píxeles y quedaban abiertas (algunas ya
corregidas arriba: F1, F4, F8, F16, F17, F18, F19; quedan las de esta tabla), y encontró que una de las
"3 resueltas" (orden de gates) **contradecía** el diagrama de Fase 1. Se corrige la tabla completa:

```
  DECISIÓN NECESARIA                                  | SI SE DIFIERE, QUÉ PASA
  ------------------------------------------------------|---------------------------------------------
  Orden de gates cuando hay video Y ubicación (F14/F15) | Fase 1 y Fase 2 daban órdenes opuestos en el
                                                          | mismo documento — el implementador sigue una
                                                          | u otra al azar
  Label del botón final ("Start Call" vs "Continue")     | Con 2 gates en secuencia, un label fijo
  cuando hay 2 gates en secuencia (F14)                  | "Start Call" en el primer gate es una mentira
                                                          | (la llamada no empieza ahí)
  ¿"Additional directions" (texto libre) es ground       | Si se incluye en el matching, alta tasa de
  truth puntuable o solo descriptivo?                    | falsos negativos (texto libre no tiene hints)
  ¿Cuándo se muestra el gate — qué cuenta como           | Tres call sites (validación del editor,
  "location configured"? (F8)                            | condición del gate, inclusión en scoring)
                                                          | inventan 3 reglas distintas si no se fija una
  ¿Un marcador sin ningún campo de texto cuenta como     | Gate se muestra con un flag flotando sin
  "configurado"? (F8)                                    | ninguna etiqueta legible
```

**Decisión 1 (corregida — F14/F15): location briefing primero, video gate segundo, `call.start` al
final.** Razonamiento sin cambios (la ubicación es el contexto de la escena, el video es la evidencia del
incidente) — lo que cambia es que ahora Fase 1 (Sección 1, diagrama de arquitectura; Sección 4, tabla de
edge cases; 0E) se corrigió para decir lo mismo, eliminando la contradicción que la voz independiente
encontró.

**Decisión 2 (nueva, F14): el botón de la pantalla de ubicación dice "Continue" cuando el escenario
también tiene video configurado, y "Start Call" cuando no.** Solo la última pantalla de la secuencia dice
"Start Call" — nunca dos pantallas seguidas con el mismo label, y nunca un label que promete algo que no
pasa inmediatamente.

**Decisión 3 (sin cambios, auto-decidida, P4 DRY):** "Additional directions" es puramente
descriptivo/narrativo — nunca entra al matching de `all_points`. Mismo razonamiento que evitó depender
del fallback genérico de `_matches_point` (0A punto 5, Fase 1).

**Decisión 4 (nueva, F8, auto-decidida P5 explicit): una sola definición de "location configured", usada
en los 3 call sites.** El gate de pre-llamada, la validación de guardado del editor, y la inclusión en
`all_points` usan la MISMA regla: *al menos uno de street/cross_street/landmark es no-vacío*. Un marcador
posicionado sin ningún campo de texto **no** cuenta — el editor bloquea guardar esa combinación con un
mensaje inline (mismo primitivo `.call-notice.error` de Pass 2).

**Decisión 5 (sin cambios, ya incorporada en Pass 4/5):** ícono de línea fina, `stroke-width:1.7`, sin
relleno, sin sombra; rosa de los vientos de 4 marcas — ver tabla de tokens de Pass 5.

## Required Outputs — Fase 2 (Design)

### "NOT in scope"
1. **Mockups visuales generados (PNG).** `DESIGN_NOT_AVAILABLE` verificado (sin credenciales OpenAI) —
   se usan wireframes ASCII en su lugar, igual que la revisión de video.
2. **Soporte mobile/tablet.** Piso de `1180px` es una decisión preexistente, no un descuido.
3. **Indicación en vivo de "vas bien/mal" mientras se habla** (progreso parcial puntuado en tiempo real)
   — distinto del acceso opt-in a re-consultar el mapa (F12, en alcance): esto sí invalidaría el
   ejercicio, aquello no.
4. **`/design-consultation` completo / `DESIGN.md` formal.** Gap real, no bloqueante — ya es TODO
   pendiente de la revisión de video, no se duplica.
5. **Editor de mapa con líneas de calle en cualquier ángulo** (Approach B, Fase 1) — el lienzo de F17
   dibuja calle/cruce como una cruz ortogonal simple, no geometría libre; sigue siendo "básico/ficticio."

### "What already exists"
`.panel`, `.functional-review-grid`, `.empty-copy`, `.call-notice.error`, paleta completa de 21 tokens
(Pass 5), patrón `AreaChart`, y sobre todo `PreCallVideoGate.tsx` + `InCallVideoPanel.tsx` como
precedente directo tanto de la pantalla de pre-llamada como del acceso opt-in en vivo — todos reutilizados,
ninguno reconstruido.

### TODOS.md updates
1. **Qué:** verificar contraste de `--muted` sobre `--bg-deep` para las etiquetas de calle del mini-mapa.
   **Por qué:** mismo gap ya anotado (no verificado) en la revisión de video, ahora con una segunda
   superficie que lo necesita. **Effort:** S. **Priority:** P2, atado a T7 de la revisión de video.
   **Decisión:** Add to TODOS.md (mismo ítem, no duplicar).
2. **Qué:** toggle "Preview trainee view" en la sección de autoría del editor. **Por qué:** hallazgo F9
   — el autor escribe contenido que el trainee lee verbatim y hoy no tiene forma de verlo tal cual se
   vería en `PreCallLocationBriefing`. **Effort:** S. **Priority:** P2 — valioso pero no bloqueante (el
   autor puede guardar y abrir una llamada de prueba como workaround).
   **Decisión:** Add to TODOS.md, no bloquea el alcance mínimo.

## Implementation Tasks — Fase 2 (Design)

```markdown
- [ ] **T1 (P1, human: ~6-8h / CC: ~1.5-2h)** — location-minimap-component — Construir
  `LocationMiniMap.tsx` (3 modos: author/brief/review), dibujando geometría real (F17: calle horizontal,
  cruce vertical, landmark como cuadrado, flag con offset respecto a la intersección) con los tokens de
  Pass 5, navegación por teclado con nudge de flechas + aria-live (F18)
  - Surfaced by: Pass 1 (F17), Pass 4, Pass 5, Pass 6 (F18)
  - Files: frontend/src/components/LocationMiniMap.tsx (nuevo), frontend/src/styles/globals.css
  - Verify: navegación completa por teclado sin mouse; contraste de labels ≥4.5:1; el flag se posiciona
    visualmente relativo a la calle/cruce dibujados, no flotando en un lienzo vacío
- [ ] **T2 (P1, human: ~4-5h / CC: ~1h)** — precall-location-briefing — Construir
  `PreCallLocationBriefing.tsx`: mapa→texto→briefing (con `max-height`+scroll, F4)→botón con label
  condicional (F14), gate de "location configured" con una sola definición compartida (F8), fallo de
  carga marca `location_delivered:false` sin penalizar (F6)
  - Surfaced by: Pass 1, Pass 2 (F6), Pass 7 (F8, F14)
  - Files: frontend/src/components/PreCallLocationBriefing.tsx (nuevo), frontend/src/pages/CallPage.tsx
  - Verify: escenario sin ubicación configurada omite el gate; fallo de carga no cuenta como "missing"
    en el score; briefing largo no desborda `.call-card`
- [ ] **T3 (P1, human: ~2h / CC: ~30min)** — in-call-location-panel — Construir
  `InCallLocationPanel.tsx`, mismo patrón que `InCallVideoPanel.tsx` (cerrado por default, botón opt-in
  "Check the address again")
  - Surfaced by: Pass 1, Pass 3 (F12, F13)
  - Files: frontend/src/components/InCallLocationPanel.tsx (nuevo), frontend/src/pages/CallPage.tsx
  - Verify: panel cerrado por default; abrirlo/cerrarlo no afecta el estado de la llamada
- [ ] **T4 (P1, human: ~2-3h / CC: ~30-45min)** — editor-location-section — Sección "Incident location"
  en `ScenarioEditorPage.tsx`: texto primero (F3), gateada por `isEditing` (F9), "Remove location",
  validación de guardado usando la definición compartida de "configured" (F8)
  - Surfaced by: Pass 1 (F3, F9), Pass 7 (F8)
  - Files: frontend/src/pages/ScenarioEditorPage.tsx
  - Verify: no se puede guardar un marcador sin texto; sección oculta hasta que el escenario ya existe
- [ ] **T5 (P2, human: ~2h / CC: ~30min)** — session-breakdown-location — Bloque anidado en
  "Information Collected" (no panel nuevo, F2) con check-lines por campo desde
  `evaluation.location_detail`, mapa modo review con overlay verde/gris
  - Surfaced by: Pass 1 (F1, F2), Pass 2
  - Files: frontend/src/components/SessionBreakdown.tsx
  - Verify: sesión histórica sin `location_detail` oculta la subsección; `location_delivered:false`
    muestra "not scored", nunca "0%"
```

### Completion Summary — Fase 2 (Design)
```
  +====================================================================+
  |         DESIGN PLAN REVIEW — COMPLETION SUMMARY (Fase 2)            |
  +====================================================================+
  | System Audit         | sin DESIGN.md; auditoría corregida a los 21 |
  |                       | tokens reales (Pass 5); scope UI: 5 piezas  |
  |                       | de UI nuevas, no 3                          |
  | Step 0               | rating inicial 4/10, foco: las 7 dimensiones|
  | Pass 1  (Info Arch)  | 4/10 → 8/10 (corregido: geometría real F17) |
  | Pass 2  (States)     | 2/10 → 8/10 (corregido: primitivos reales,  |
  |                       | fairness fix F6)                            |
  | Pass 3  (Journey)    | 5/10 → 8/10 (corregido: pedagogía F12/F13)  |
  | Pass 4  (AI Slop)    | 7/10 → 9/10 (+ corrección de idioma F19)    |
  | Pass 5  (Design Sys) | 3/10 → 8/10 (auditoría completa, no 2/21)   |
  | Pass 6  (Responsive) | 6/10 → 8/10 (fix de a11y corregido, F18)    |
  | Pass 7  (Decisions)  | 5 resueltas (2 corrigen contradicciones     |
  |                       | previas), 0 diferidas                       |
  +--------------------------------------------------------------------+
  | NOT in scope         | escrito (5 items)                            |
  | What already exists  | escrito                                      |
  | TODOS.md updates     | 2 items                                      |
  | Approved Mockups     | 0 generados (sin credenciales OpenAI) —      |
  |                       | wireframes ASCII usados en su lugar          |
  | Decisions made       | 5 (Pass 7) + 3 correcciones cross-fase       |
  |                       | (cherry-pick #8 y orden de gates en Fase 1)  |
  | Decisions deferred   | 0                                             |
  | Overall design score | 4/10 → 8/10 (promedio de las 7 pasadas,      |
  |                       | tras incorporar la voz independiente)        |
  +====================================================================+
```

**PHASE 2 COMPLETE.** Codex: no disponible. Claude subagent: 19 hallazgos (5 CRÍTICO), incluyendo una
corrección que revierte una decisión ya tomada en Fase 1 (cherry-pick #8) y dos contradicciones internas
entre Fase 1 y Fase 2 (orden de gates, idioma de UI) — todas incorporadas arriba. Consensus: sin voz de
Codex disponible, `[subagent-only]`; la corrección se trata como CONFIRMADA porque cada hallazgo se
verificó contra el código real (`InCallVideoPanel.tsx`, `globals.css`, `.call-card`), no como opinión.
Passing to Phase 3 (Eng Review).

---

# Fase 3 — Eng Review

## Step 0 — Scope Challenge

**Qué código existente ya resuelve cada sub-problema:** ver 0B (Fase 1) — el 100% de la mecánica
(ground-truth con hints, tabla 1:1 sin `ALTER TABLE`, gate de pre-llamada, panel opt-in en vivo, split
autoría/trainee) tiene precedente directo en el código de video ya shippeado. Nada de esto se construye
desde cero.

**Mínimo que logra el objetivo:** confirmado en 0D (Fase 1), ajustado por las correcciones de Fase 2 —
el "core" ahora incluye el `InCallLocationPanel` (antes cherry-pick opcional, ahora alcance mínimo tras
F12) y `evaluation.location_detail` (antes implícito, ahora explícito tras F1).

**Complexity check — corregido tras la voz independiente (hallazgo B7): el conteo real es ~19 archivos,
no 10.** El borrador inicial omitió: `server_main.py` (wiring del store nuevo, mismo punto donde se
conecta `sqlite_scenario_video_store.py`), `frontend/src/types.ts` (tipos + variante de `EngineCommand`),
`frontend/src/lib/api.ts` (funciones de fetch nuevas), `frontend/src/stores/engineStore.ts` (estado +
loader), `test_scoring.py`/`test_server_app.py`/`test_shared_sqlite_topology.py` (tests del store nuevo
sumándose a los 6 stores ya enumerados por nombre en ese archivo), y `migrate_seed_locations.py` (el
propio cherry-pick de Sección 2 punto 6). **Dispara el umbral de complejidad con más margen del que el
borrador inicial calculó.**

**Auto-decisión (P2 boil lakes, no se reduce — recalculada sobre el número correcto):** cada cambio sigue
siendo angosto y con precedente 1:1 en código ya shippeado; el conteo más alto no cambia esa propiedad,
solo la estimación de esfuerzo (ver Implementation Tasks, effort actualizado). El plan no se reduce por
las mismas razones que antes (`InCallLocationPanel` es alcance mínimo tras F12), pero el rediseño de
scoring de esta fase (ver Section 1 corregida abajo) SÍ elimina una clase entera (`LocationGroundTruthPoint`)
y un subsistema completo (`location_delivered`/WS command/staleness guard) que el borrador inicial había
sumado sin necesidad — el conteo de ~19 ya refleja esa simplificación, no la contradice.

**Search check:** patrón de geometría SVG con líneas + texto posicionado (`street`/`cross_street` como
ejes, ver F17) es un patrón nativo de SVG (`<line>` + `<text>`), sin librería externa — **[Layer 1]**, no
se justifica una librería de mapas/diagramas para esto. Navegación por teclado con nudge de flechas +
`aria-live` (F18) es el patrón WAI-ARIA estándar para "slider"/"application" custom — **[Layer 1]**, sin
librería nueva. Ninguno de los dos introduce una dependencia nueva a `package.json`.

**TODOS cross-reference:** `TODO-20` (migraciones SQLite) ya cubre el patrón de tabla nueva que este plan
sigue — no bloquea, se referencia. `TODO-16` (RBAC) no bloquea (0A punto 7, Fase 1). Este plan agrega 2
TODOs nuevos (contraste de `--muted`, ya existente — no duplicado; preview de vista de trainee).

**Completeness check:** el plan ya incorpora la versión completa (con `InCallLocationPanel`, con
`evaluation.location_detail`, con la definición única de "configured," con el fix de equidad F6) en vez
de una versión recortada — no hay un atajo pendiente de "boil the ocean" que quede fuera aquí; los únicos
recortes reales (Approach B, multi-marcador) tienen justificación explícita de alcance, no de ahorro de
esfuerzo.

**Distribution check:** N/A — no se introduce ningún artefacto nuevo (binario, paquete, imagen) fuera del
propio código de la app ya distribuido por el pipeline existente.

## Section 1 — Architecture Review (extiende Fase 1 Sección 1, corregida tras voz independiente)

**Nota de corrección [CRÍTICA, hallazgos A3/B1/B2/B4/B5/B8]:** el diseño de scoring del borrador inicial
tenía un problema de fondo, no un detalle: (1) `LocationGroundTruthPoint` con `label` = valor real
configurado activa exactamente el fallback de coincidencia por palabra suelta de `_matches_point`
(`scoring.py:184`, verificado — `"5th Avenue".lower().split()` produce `"avenue"`, 6 caracteres, que
matchea CUALQUIER transcript que contenga esa palabra en cualquier contexto) — el mismo bug que 0A-5 creía
haber evitado; (2) el mecanismo `location_delivered` (fallo de carga → excluir de `all_points`) es un
**client-controlled scoring exemption**: el trainee gana puntaje con solo apretar "Skip", porque remover
un punto `required` de `all_points` reduce el denominador de `_completeness` (`scoring.py:197`); (3) esto
requiere un campo/comando WS nuevo sin hogar de persistencia claro y sin guard de staleness (el mismo
problema que `video.ended` sí resuelve, `app.py:916-920`, y que el borrador nunca replicó; (4) un solo
punto combinado no puede dar el desglose por campo que Fase 2 pidió para el mapa de revisión sin una
estructura paralela frágil (`evaluation.location_detail`); (5) `LocationGroundTruthPoint` es idéntico
campo-por-campo a `CriticalDataPoint` ya existente — una clase nueva para cero diferencial. **Se
rediseña la integración de scoring completa, más simple que el borrador original, no más compleja:**

**Modelo de datos — `ScenarioLocation` (nuevo, autoría/visualización) + reutilización directa de
`CriticalDataPoint` (scoring, sin clase nueva):**
```python
@dataclass
class ScenarioLocation:
    scenario_id: str
    street: str = ""
    cross_street: str = ""
    landmark: str = ""
    city_or_zone: str = ""
    additional_directions: str = ""   # narrativo — NUNCA entra a scoring (Fase 2 Pass 7 decisión #3)
    match_hints: list[str] = field(default_factory=list)   # sinónimos extra, autor-editable, por-escenario
    marker_x: float | None = None      # None = "no posicionado" — corrige B10 (F8 necesita distinguir
    marker_y: float | None = None      # "sin marcador" de "marcador en el default 0.5,0.5")
    created_at: float = 0.0            # float, no str — corrige A1 (consistente con ScenarioVideo)
    updated_at: float = 0.0

@runtime_checkable
class ScenarioLocationPort(Protocol):        # corrige A1 — @runtime_checkable como el resto de ports.py
    def get(self, scenario_id: str) -> ScenarioLocation | None: ...
    def upsert(self, location: ScenarioLocation) -> None: ...   # -> None, corrige A1 (mismo shape que video)
    def delete(self, scenario_id: str) -> None: ...
```

**`CriticalDataPoint` gana 2 campos opcionales, default-compatibles con TODO lo ya autorado hoy (corrige
A3 y B5, sin clase nueva — corrige B8):**
```python
@dataclass
class CriticalDataPoint:
    key: str
    label: str
    required: bool = True
    match_hints: list[str] = field(default_factory=list)
    word_fallback: bool = True          # NUEVO — False desactiva el último-recurso de _matches_point
    counts_toward_timing: bool = True   # NUEVO — False lo excluye de _time_to_critical_data
```
`_matches_point` (scoring.py:184) cambia una línea: el fallback por palabra suelta solo corre `if
point.word_fallback`. `_time_to_critical_data` filtra su input a `[p for p in points if
p.counts_toward_timing]` antes de buscar la primera mención. Ambos defaults son `True` — **cero cambio de
comportamiento para cualquier `CriticalDataPoint` autorado hoy** (video, escenarios de texto existentes).

**Regla de "configured" única — corregida (hallazgo B9): vive en `core/scoring.py` (lógica de dominio),
no en `core/ports.py` (que hoy son solo dataclasses/Protocols/excepciones, sin comportamiento):**
```python
def is_location_configured(loc: ScenarioLocation | None) -> bool:
    if loc is None:
        return False
    return bool(loc.street.strip() or loc.cross_street.strip() or loc.landmark.strip())
```
El endpoint `PUT /scenarios/{id}/location` es la única fuente de verdad — rechaza con 422 (mismo patrón
que la validación de rango de video, `app.py:424-432`) un guardado donde `is_location_configured()` sea
`False` pero `marker_x`/`marker_y` no sean `None` (marcador sin texto). El editor en TypeScript
**duplica** la misma regla solo como UX (deshabilitar el botón antes de golpear el 422) — se documenta
explícitamente que es una copia no autoritativa, no "una sola función compartida" (corrección honesta de
B9: Python y TypeScript no pueden compartir una función real aquí).

**Persistencia (nueva, `persistence/sqlite_scenario_location_store.py`, corregida contra el patrón real
de `sqlite_scenario_video_store.py`, verificado línea por línea):**
```sql
CREATE TABLE IF NOT EXISTS scenario_locations (
  scenario_id TEXT PRIMARY KEY,
  street TEXT NOT NULL DEFAULT '',
  cross_street TEXT NOT NULL DEFAULT '',
  landmark TEXT NOT NULL DEFAULT '',
  city_or_zone TEXT NOT NULL DEFAULT '',
  additional_directions TEXT NOT NULL DEFAULT '',
  match_hints_json TEXT NOT NULL DEFAULT '[]',
  marker_x REAL,
  marker_y REAL,
  created_at REAL NOT NULL DEFAULT 0.0,
  updated_at REAL NOT NULL DEFAULT 0.0
)
```
`__init__(self, db_path: str, clock=time.time)` — mismo constructor inyectable que el resto de stores;
`upsert()` aplica `location.created_at = location.created_at or clock()` antes de escribir, igual que
`ScenarioVideo`. PK = `scenario_id` (1:1, igual que `scenario_videos`), nunca `ALTER TABLE scenarios`
(TODO-20). **Nota honesta (corrige A1):** ningún store existente en este repo configura `busy_timeout`
en `sqlite3.connect()` — `test_shared_sqlite_topology.py` ya documenta esto como riesgo pre-existente,
no introducido por este plan. Este store se agrega a la lista de stores que ese test enumera por nombre
(Implementation Tasks, T-backend) — no se inventa un rescate de `sqlite3.OperationalError` que hoy no
existe (el borrador inicial lo afirmaba incorrectamente).

**API (server/app.py, mismo patrón que los modelos de video):** `ScenarioLocationIn`/`ScenarioLocationOut`
(autoría, incluye `match_hints`) vs. `ScenarioLocationAccessOut` (trainee — street/cross_street/landmark/
marker_x/marker_y/additional_directions, **sin** `match_hints`). `marker_x`/`marker_y` validados
`Field(ge=0.0, le=1.0)` cuando no son `None` (corrige B10 — el endpoint de video sí valida rangos,
`app.py:424-432`, este no lo hacía). Endpoints: `PUT/GET/DELETE /scenarios/{id}/location` (autoría) +
`GET /scenarios/{id}/location/brief` (trainee, stripped).

**Corrección de seguridad honesta (hallazgo B12, refuerza 0A-7 de Fase 1 en vez de contradecirlo):** el
split autoría/trainee **no es un control de acceso** — `GET /scenarios/{id}` ya devuelve
`match_hints` completos a cualquier bearer token hoy (`ScenarioOut` extiende `ScenarioIn`), y el mismo
patrón aplicaría aquí. Es una convención anti-spoiler de UX (el cliente de trainee simplemente no pide/
muestra el campo), no una barrera — se dice explícitamente en vez de presentarlo como protección real.

**Capa de responsabilidad — geometría es SOLO frontend, no backend (verificado, sin fugas — el único
hallazgo de esta capa fue B10, ya corregido arriba: `marker_x/y` deben validarse en rango aunque el
backend no interprete su significado geométrico).** El backend nunca calcula la posición de las líneas de
calle/cruce en píxeles — solo persiste texto + 2 floats opcionales. `LocationMiniMap.tsx` es el único
lugar que traduce esos datos a geometría SVG (F17).

**Integración con `score_session` (`core/scoring.py`) — simplificada, sin clase nueva, sin campo de
sesión nuevo, sin comando WS nuevo:**
```python
def _location_critical_points(location: ScenarioLocation | None) -> list[CriticalDataPoint]:
    if not is_location_configured(location):
        return []  # nunca puntos vacíos que siempre fallan
    points = []
    for field_key, field_label, value in (
        ("street", "Street", location.street),
        ("cross_street", "Cross street", location.cross_street),
        ("landmark", "Landmark", location.landmark),
    ):
        if value.strip():
            points.append(CriticalDataPoint(
                key=f"location_{field_key}",
                label=f"{field_label}: {value}",          # honesto y único — ya no genérico (0A-5)
                match_hints=[value, *location.match_hints],
                required=True,
                word_fallback=False,          # corrige A3 — el fallback de palabra suelta se desactiva
                counts_toward_timing=False,   # corrige B5 — no infla time_to_critical_data (30% peso)
            ))
    return points
```
Se concatena a `all_points` exactamente como `video_ground_truth` hoy — **sin excepción, sin bandera de
"delivered", sin exención de scoring** (corrige B1/B2 de raíz: el trainee que aprieta "Skip" en la
pantalla de pre-llamada sigue siendo evaluado contra la ubicación configurada, igual que hoy un trainee
que se salta el video sigue siendo evaluado contra `video_ground_truth`, `app.py:913,927`). El botón
"Skip, start call" existe por ritmo/UX (mismo precedente que video), nunca por exención de puntaje.

**Render en `SessionBreakdown` — cero estructura nueva de datos (corrige B3/B4/B13 de una vez):** los 3
puntos de ubicación (cuando existen) aparecen en los arrays `collected`/`missing` **ya existentes**, con
labels legibles ("Street: 5th Avenue") — el mismo mecanismo genérico que ya renderiza cualquier
`CriticalDataPoint` sin cambios de frontend (0B, Fase 1). El único componente nuevo de verdad es
`LocationMiniMap mode="review"`, que colorea la calle/cruce/landmark dibujados en verde/gris comprobando
si su label (`"Street: ..."`) está en `evaluation.collected` — sin campo `location_detail` nuevo, sin
timestamp de "primera mención" (que tenía un bug de shape epoch-vs-relativo, B13 — ya no aplica porque no
existe ese campo). Como el scoring corre una sola vez en `finish_call()` y se persiste en
`evaluation_json`, el snapshot histórico es automático — editar la ubicación del escenario después no
cambia sesiones ya puntuadas (corrige B3 sin código adicional, por la misma razón que ya protege a
cualquier otro `CriticalDataPoint` hoy).

## Section 2 — Code Quality Review

1. **DRY:** `is_location_configured()` en un solo lugar (`core/scoring.py`, corregido de `ports.py`, B9);
   `_location_critical_points()` reutiliza `CriticalDataPoint`/`_matches_point` sin clase paralela
   (corrige B8); `LocationMiniMap.tsx` con 3 modos en vez de 3 componentes.
2. **Separación de capas:** la geometría vive solo en frontend, verificado sin fugas salvo la validación
   de rango de `marker_x/y` (B10, ya corregida en Sección 1 — el backend valida el rango sin interpretar
   el significado geométrico, que sigue siendo responsabilidad exclusiva de `LocationMiniMap.tsx`).
3. **Naming:** `ScenarioLocationAccessOut` (trainee) vs. `ScenarioLocationOut` (autoría), mismo sufijo que
   el par de video. Labels de los puntos de scoring (`"Street: 5th Avenue"`) son auto-descriptivos, no
   genéricos (corrige 0A-5 de verdad esta vez, vía `word_fallback=False`, no vía naming por sí solo).
4. **Over-engineering check:** no se justifica un modelo de geometría genérico/plugin — 3 primitivas
   fijas (línea, línea, cuadrado) alcanzan (0C-bis Approach A). Tampoco se justifica una estructura de
   reporte paralela (`location_detail`) cuando `collected`/`missing` ya existentes la resuelven — el
   rediseño de Sección 1 ELIMINA esa sobre-construcción del borrador inicial.
5. **Under-engineering check (corregido, hallazgos B1/B2):** el borrador inicial estaba, en realidad,
   under-engineered en la dirección opuesta a la que decía — `location_delivered` parecía "una excepción
   de equidad cuidadosa" pero era una superficie de scoring controlada por el cliente sin persistencia
   real ni protección de staleness. El rediseño de Sección 1 la elimina en vez de completarla — la
   ausencia total del mecanismo es la corrección, no una simplificación insuficiente.
6. **Migración de datos (0A punto 6, Fase 1) — mejora de ingeniería, sin cambios:** `migrate_seed_locations.py`
   pre-llena un borrador de `ScenarioLocation` a partir del `CriticalDataPoint` ad-hoc existente
   (`last_location`/`address`/`location`) para que el supervisor revise/complete en vez de retipear.
   Nota: tras el rediseño de Sección 1, este script también debe **retirar** el punto ad-hoc original del
   escenario migrado (ya lo decía 0B de Fase 1) — de lo contrario el mismo hecho se cuenta dos veces con
   dos labels distintos ("Location" viejo + "Street: ..." nuevo), inflando completeness artificialmente.
   Se agrega como paso explícito del script, no como nota aparte.
7. **Redundancia de store (hallazgo A1, corregido en Sección 1):** el store nuevo ahora sigue el patrón
   real de `sqlite_scenario_video_store.py` campo por campo (float timestamps, `clock` inyectado,
   `upsert() -> None`, `@runtime_checkable`) — no una variación que diverge sin razón.

## Section 3 — Test Review

**Detección de framework — corregida (hallazgo B6): el frontend no tiene NINGÚN test runner hoy,
verificado.** Python: `pyproject.toml` presente → `pytest` (confirmado por `test_scoring.py`,
`test_scenarios.py`, `test_scenario_videos.py` ya existentes). Frontend: `package.json` no declara
vitest/jest/playwright ni script `"test"` — solo vite/electron/tsc. **Esto no es un detalle a verificar
después; cambia lo que este plan puede prometer.** El borrador inicial marcó 2 flujos de frontend como
`[→E2E]` obligatorios mientras afirmaba, en el mismo documento (Step 0, "Search check"), que "ninguno de
los dos introduce una dependencia nueva a `package.json`" — contradicción real. Se corrige: los tests de
frontend/UI de esta fase se degradan a **checklist de QA manual** (ya cubierto por el Test Plan Artifact
abajo, que alimenta `/qa`), y se agrega un TODO explícito (no bloqueante para este plan) para introducir
un toolchain de test de frontend — cross-cutting, no exclusivo de esta feature.

**Diagrama de cobertura (código Python = testeable con pytest hoy; flujos de UI = checklist de QA manual,
hallazgo B6):**

```
CODE PATHS (pytest, testeables hoy)                          USER FLOWS (checklist de QA manual — B6,
                                                               sin toolchain de test de frontend hoy)
[+] core/scoring.py
  ├── is_location_configured()                               [+] Scenario authoring
  │   ├── [GAP] None → False                                   ├── [GAP-QA] Save con 1-3 campos de texto
  │   ├── [GAP] todos vacíos → False                            ├── [GAP-QA] Bloqueo: marcador sin texto (F8/B10)
  │   └── [GAP] al menos 1 no-vacío → True                      ├── [GAP-QA] Remove location (F9)
  ├── _location_critical_points()                               └── [GAP-QA] Preview trainee view (TODO, no bloq.)
  │   ├── [GAP] location None → []
  │   ├── [GAP] 1/2/3 campos no-vacíos → 1/2/3 points          [+] Pre-call briefing
  │   ├── [GAP] label = "Street: <valor>" (nunca genérico)      ├── [GAP-QA] Location configured → gate shows
  │   └── [GAP] word_fallback=False, counts_toward_timing=False ├── [GAP-QA] Not configured → gate omitido,
  ├── _matches_point() con word_fallback=False                  │            sin cambio de comportamiento
  │   ├── [GAP] [→REGRESIÓN A3] "avenue" suelto en transcript   ├── [GAP-QA] "Skip" → sigue evaluado (B1 fix)
  │   │        NO matchea un point con word_fallback=False      └── [GAP-QA] Briefing largo → scroll (F4)
  │   └── [GAP] match_hints completo SÍ matchea (comportamiento
  │        sin cambios para hints, solo se apaga el fallback)  [+] In-call
  ├── _time_to_critical_data() con counts_toward_timing=False    ├── [GAP-QA] Panel cerrado por default
  │   └── [GAP] [→REGRESIÓN B5] puntos de ubicación NUNCA        └── [GAP-QA] Toggle no afecta la llamada
  │        adelantan ni atrasan esta categoría (30% peso)
  └── score_session() — fusión incondicional a all_points       [+] Video + location ambos configurados
      ├── [GAP] sin ubicación → sin cambio de score              ├── [GAP-QA] Orden: location→video→call.start
      └── [GAP] [→REGRESIÓN TODO-17] transcript sintético que    │            (F15), sin doble "Start Call" (F14)
          menciona la calle real configurada → collected,        └── [GAP-QA] Sin double-fire de call.start (B11)
          no missing
[+] persistence/sqlite_scenario_location_store.py              [+] Session review
  ├── [GAP] get() sin fila → None (no raise)                    ├── [GAP-QA] collected/missing muestran
  ├── [GAP] upsert() crea, actualiza, aplica clock si            │            "Street: ..." sin estructura nueva
  │        created_at es 0.0 (mismo patrón que video)            ├── [GAP-QA] Mapa review colorea verde/gris
  ├── [GAP] delete()                                             │            comprobando membership en collected
  └── [GAP] agregado a test_shared_sqlite_topology.py (A1)       └── [GAP-QA] Sesión histórica sin datos →
[+] server/app.py — endpoints                                                subsección oculta
  ├── [GAP] PUT /scenarios/{id}/location — 422 si marcador
  │        sin texto (B10); 200 + persiste si válido
  ├── [GAP] GET .../location/brief — sin match_hints
  ├── [GAP] marker_x/y fuera de [0,1] → 422 (B10)
  └── [GAP] escenario sin ubicación → null, no 500
[+] server_main.py — wiring del store nuevo (B7, antes omitido)
  └── [GAP] instanciado y pasado a los handlers, mismo punto que scenario_video_store

LLM integration: NINGUNA en este plan (rule-based) — sin [→EVAL] nuevo.

COVERAGE: 0/19 code paths tested (plan nuevo, ningún test escrito todavía) + 15 flujos de UI en checklist
manual (no automatizables hoy sin agregar un toolchain de test de frontend, TODO no-bloqueante, B6)
QUALITY: N/A hasta implementación  |  GAPS: 19 code paths + 15 flujos manuales
```

**Matriz E2E — corregida (B6): ningún ítem se marca `[→E2E]` porque no hay toolchain de frontend hoy.**
Los dos flujos que lo ameritarían por naturaleza (secuencia location→video, regresión TODO-17) se dividen
así: la regresión TODO-17 se prueba **end-to-end en pytest puro** (transcript sintético →
`score_session()` → `evaluation.collected`, sin frontend involucrado — sí es automatizable hoy). La
secuencia de gates en `CallPage.tsx` (F15/B11) queda como checklist de QA manual hasta que exista
infraestructura de test de frontend — marcado `[GAP-QA]`, no `[→E2E]`, para no prometer algo que el repo
no puede correr hoy.

**REGRESIÓN [mandatory, IRON RULE] — corregida (hallazgo B5, la aserción "mismo score" del borrador
inicial era irrealizable):**
1. Sesión sin ubicación configurada → `evaluation` idéntico al de hoy (test de no-regresión, sí realizable
   porque `_location_critical_points()` retorna `[]` y `all_points` queda sin cambios).
2. El escenario semilla `traffic_accident` YA tiene un `CriticalDataPoint` de ubicación ad-hoc. **Corregido:**
   no se afirma "mismo score tras migrar" (imposible — cambia el denominador de completeness de 6 a un
   número distinto sin importar cómo se migre). Se afirma en cambio: (a) antes de migrar, el punto ad-hoc
   sigue funcionando exactamente igual que hoy (test de no-regresión real); (b) el script de migración
   (Sección 2 punto 6) retira el punto ad-hoc en el mismo commit que agrega `ScenarioLocation`, así que
   nunca hay un estado intermedio con doble conteo — se prueba con un test de golden-value que fija el
   score esperado ANTES y DESPUÉS de la migración como dos valores distintos y documentados, no como
   "igual."
3. **Nueva (hallazgo B5):** `_time_to_critical_data` con los 3 puntos de ubicación presentes debe producir
   el MISMO resultado que sin ellos (porque `counts_toward_timing=False` los excluye) — test explícito de
   que agregar ubicación no adelanta artificialmente el 30% de peso de esa categoría.

**Test Plan Artifact:** escrito a
`~/.gstack/projects/hhce2303-SIG-Agent/hcruz-feature-video-scenarios-eng-review-test-plan-20260821.md`
(contenido resumido abajo; `jq`/agregador JSONL omitido, no instalado, igual que fases anteriores):

```markdown
# Test Plan — Ubicación del incidente
## Affected Pages/Routes
- Scenario editor — nueva sección "Incident location"
- Pre-call flow (CallPage) — nuevo gate + panel opt-in en vivo
- Session review (SessionBreakdown) — nueva subsección

## Key Interactions to Verify
- Guardar ubicación con 1, 2, 3 campos de texto en el editor
- Bloqueo de guardado si solo hay marcador sin texto (F8)
- Gate de pre-llamada aparece/se omite según haya o no ubicación configurada
- Panel en vivo cerrado por default, opt-in funcional
- Secuencia location→video cuando ambos existen (F15)
- Botón "Continue" vs "Start Call" según haya o no un gate siguiente (F14)

## Edge Cases
- Fallo de carga de la ubicación → Skip, no penaliza el score (F6)
- Briefing largo desborda el contenedor con scroll, no corta contenido (F4)
- Nombre de calle largo en el mapa → trunca con `title` completo (F11)
- Sesión histórica sin datos de ubicación → subsección oculta

## Critical Paths
- Regresión TODO-17: transcript sintético que menciona la calle configurada → `collected`, no `missing`
- Escenario `traffic_accident` (ya migrado) sigue puntuando consistente, sin doble conteo
```

## Section 4 — Performance Review

**N+1 / DB access — corregido (hallazgo A2, la afirmación original era falsa en dos puntos verificados):**
el borrador inicial citó "`server/app.py:956`" como el único punto de fetch de `call.start`; esa línea es
en realidad parte de la llamada a `metrics_judge` dentro de `finish_call`, no `call.start`. El fetch real
de video en `call.start` está más adelante en ese handler (`active_video =
scenario_video_store.get(scenario.id) if scenario_video_store else None`). Más importante: **`get()` no
se llama una sola vez por sesión — `_has_video()` lo llama una vez por escenario** dentro de
`_scenario_summary`/`_scenario_out`, que a su vez corren una vez por escenario en cada `GET /scenarios` y
en el WS `scenarios.list` — un N+1 **ya existente** en el listado de escenarios. Mirrorear el mismo patrón
con `has_location` **duplica** ese N+1 existente (2 queries por escenario listado en vez de 1).
**Impacto real hoy:** despreciable — 3 escenarios semilla. **Corrección honesta, no ignorada:** se agrega
`list_configured_scenario_ids() -> set[str]` a ambos ports (video y location) para que el listado de
escenarios haga 1 query por store en vez de N — cherry-pick de Sección 2/Implementation Tasks, no
bloqueante para este plan pero sí para cuando el catálogo de escenarios crezca más allá de un puñado.

**Memoria:** el payload de `ScenarioLocation` es texto corto + 2 floats opcionales — despreciable.

**Caching:** no se justifica a la escala actual — mismo argumento que video.

**Rutas lentas:** ninguna — sin llamadas de red nuevas, matching determinista y local, igual que el resto
de `scoring.py` hoy. `word_fallback=False`/`counts_toward_timing=False` no agregan costo — son chequeos
booleanos en un loop que ya existe.

## Eng Dual Voices

CODEX SAYS (eng — architecture challenge): *(no disponible — codex no instalado)*.

CLAUDE SUBAGENT (eng — independent review): 26 hallazgos, verificando línea por línea contra el código
real en vez de aceptar las citas del borrador. Los más severos: (A3/CRÍTICO) el fix de 0A-5 para el
fallback de palabra suelta de `_matches_point` estaba invertido — usar el valor real como label
**activaba** el bug que decía evitar; (B1/B2/CRÍTICO) el mecanismo de equidad `location_delivered` era en
realidad una superficie de scoring controlada por el cliente, sin hogar de persistencia ni guard de
staleness; (B4/B5/HIGH) un punto combinado no puede dar desglose por campo sin una estructura paralela
frágil, y CUALQUIER punto de ubicación en `all_points` infla silenciosamente `time_to_critical_data`
(30% de peso, más que la categoría que 0A-4 ya había protegido); (A1/A2/HIGH) el store propuesto y el
performance review citaban un patrón/línea que no correspondían al código real; (B6/HIGH) el frontend no
tiene ningún toolchain de test, haciendo el 40% del plan de pruebas original irrealizable tal como estaba
escrito; (B7/MEDIUM) el conteo de archivos estaba subestimado ~2x; (B8/MEDIUM) la clase nueva
`LocationGroundTruthPoint` no tenía ningún campo que `CriticalDataPoint` no tuviera ya; (B9-B13) hallazgos
adicionales de ubicación de código, validación de rango, y un bug de shape de timestamp que dejó de
aplicar al eliminar la estructura que lo habría contenido. **Todos incorporados en las Secciones 1-4 de
arriba — el rediseño resultante es más simple que el borrador original, no más complejo: una clase menos
(`LocationGroundTruthPoint` eliminada), un subsistema menos (`location_delivered`/WS command/staleness
guard eliminado), y 2 campos booleanos nuevos en `CriticalDataPoint` en vez de ambos.**

**Consensus:** sin voz de Codex disponible, `[subagent-only]`. Cada hallazgo crítico/alto se verificó
contra el código real (`scoring.py:172-197`, `ports.py` líneas de timestamp/upsert, `app.py` fetch de
video) antes de incorporarse — no se trata como opinión sino como corrección factual, igual que en Fases
1 y 2.

## Required Outputs — Fase 3 (Eng)

### "NOT in scope"
1. **Editor de mapa interactivo con líneas dibujadas / múltiples marcadores** (Approach B, Fase 1).
2. **LLM-judge para ubicación** — se referencia `motor-de-metricas.md` (APPROVED) como el lugar natural
   para esto si la heurística de hints resulta insuficiente en uso real; no se construye especulativamente.
3. **`list_configured_scenario_ids()` (batch fetch para eliminar el N+1 de listado, A2)** — corrige un
   problema real pero pre-existente (mirrorea el mismo patrón que `_has_video` ya tiene) a escala
   despreciable hoy (3 escenarios); se agrega a TODOS.md, no bloquea este plan.
4. **Toolchain de test de frontend (vitest/playwright)** — gap real y cross-cutting (B6), no exclusivo de
   esta feature; se agrega a TODOS.md.
5. **`busy_timeout` en SQLite** — riesgo pre-existente en los 6 stores actuales (A1), no introducido por
   este plan; se referencia, no se resuelve aquí.

### "What already exists"
`_matches_point`/`CriticalDataPoint` (extendidos con 2 campos opcionales, no reconstruidos),
`sqlite_scenario_video_store.py` como patrón exacto para el store nuevo, `PreCallVideoGate.tsx`/
`InCallVideoPanel.tsx` como precedente de UI, `collected`/`missing` genéricos de `SessionBreakdown.tsx`
(cero cambios de frontend para el conteo, tras el rediseño de Sección 1) — todos reutilizados.

### TODOS.md updates (candidatos a TODO-21+, además de los ya listados en Fase 1)
1. **Qué:** `list_configured_scenario_ids()` en ambos ports (video, location) para eliminar el N+1 de
   listado de escenarios. **Por qué:** A2 — `_has_video`/`has_location` hacen 1 query por escenario
   listado; a escala pequeña es invisible, a escala grande no. **Effort:** S. **Priority:** P3 — no
   bloquea, el catálogo actual es de 3 escenarios. **Decisión:** Add to TODOS.md.
2. **Qué:** introducir un toolchain de test de frontend (vitest + @testing-library/react como mínimo
   viable). **Por qué:** B6 — hoy ningún flujo de UI es automatizable; esta feature y cualquier futura
   quedan con checklist manual únicamente. **Effort:** M. **Priority:** P2 — cross-cutting, se beneficia
   más de un due propio que de acoplarse a esta feature. **Decisión:** Add to TODOS.md.
3. **Qué:** agregar `busy_timeout` a `sqlite3.connect()` en los 7 stores (los 6 existentes + el nuevo).
   **Por qué:** A1 — `test_shared_sqlite_topology.py` ya documenta el riesgo, sin mitigación hoy.
   **Effort:** S. **Priority:** P2, mismo nivel que el resto de deuda de TODO-20. **Decisión:** Add to
   TODOS.md, referenciado a TODO-20.

### Diagrams
Los 2 diagramas ASCII de Sección 1 (Fase 1) y Sección 3 (Fase 3, cobertura) son los artefactos
requeridos — ambos ya en el documento. Comentarios de diagrama en código: `core/scoring.py` debe llevar
un comentario ASCII corto junto a `_location_critical_points()` documentando por qué `word_fallback` y
`counts_toward_timing` son `False` para estos puntos (referencia a este documento por nombre de archivo),
siguiendo la convención ya usada en `scoring.py` para `_video_reaction_seconds`.

### Failure modes
Ver Fase 1 Sección 2 (Error & Rescue Map) — sin cambios de fondo tras el rediseño, salvo que
`location_delivered` ya no es un modo de falla porque no existe. Único modo de falla nuevo real: `PUT
/scenarios/{id}/location` con `marker_x/y` fuera de rango → 422 (cubierto, B10) — no silencioso, no crítico.

### Worktree parallelization strategy

| Step | Módulos tocados | Depende de |
|------|------------------|------------|
| Backend: modelo + store + endpoints | `core/`, `persistence/`, `server/` | — |
| Backend: integración de scoring (`_location_critical_points`, flags en `CriticalDataPoint`) | `core/scoring.py` | Backend: modelo + store |
| Frontend: `LocationMiniMap.tsx` (componente aislado) | `frontend/src/components/` | — |
| Frontend: sección de autoría en `ScenarioEditorPage.tsx` | `frontend/src/pages/` | Backend: endpoints, `LocationMiniMap` |
| Frontend: `PreCallLocationBriefing` + `InCallLocationPanel` + restructuración de `CallPage.tsx` (B11, alto riesgo, secuencial en sí mismo) | `frontend/src/pages/CallPage.tsx`, `frontend/src/components/` | Backend: endpoints, `LocationMiniMap` |
| Frontend: `SessionBreakdown.tsx` (overlay de revisión) | `frontend/src/components/` | Backend: integración de scoring, `LocationMiniMap` |
| Migración: `migrate_seed_locations.py` | `persistence/`, datos | Backend: modelo + store |

**Lanes:** Lane A: Backend completo (modelo → store → endpoints → scoring), secuencial, mismo módulo.
Lane B: `LocationMiniMap.tsx` — independiente, sin dependencia de Lane A hasta integrarse (puede
desarrollarse contra props mockeadas). Lane C (espera a A+B): autoría, pre-llamada/in-call, review —
estos 3 comparten `LocationMiniMap` y los endpoints, así que corren en secuencia una vez A y B terminan,
pero entre sí tocan archivos distintos (`ScenarioEditorPage.tsx` vs. `CallPage.tsx` vs.
`SessionBreakdown.tsx`) — **paralelizables entre sí** dentro de Lane C.

**Orden de ejecución:** Lanzar A y B en paralelo (worktrees separados). Merge ambos. Luego lanzar los 3
sub-flujos de C en paralelo (3 archivos sin overlap). `migrate_seed_locations.py` corre al final, después
de que A esté mergeado — no es paralelizable con nada más porque depende del modelo final.

**Conflict flags:** ninguno — cada lane/sub-flujo toca un conjunto de archivos disjunto del resto,
excepto que Lane C completo depende de que A+B ya estén mergeados (no es un conflicto, es una dependencia
secuencial ya reflejada en el orden de ejecución).

## Implementation Tasks — Fase 3 (Eng)

```markdown
- [ ] **T-BE1 (P1, human: ~1 día / CC: ~2-3h)** — backend-location-model — `ScenarioLocation` +
  `sqlite_scenario_location_store.py` (patrón exacto de video: float timestamps, clock inyectado,
  upsert()->None, @runtime_checkable) + wiring en `server_main.py`
  - Surfaced by: Section 1 (A1, corregido)
  - Files: core/ports.py, persistence/sqlite_scenario_location_store.py (nuevo), server_main.py
  - Verify: get() sin fila retorna None; upsert() aplica clock() si created_at es 0.0
- [ ] **T-BE2 (P1, human: ~4-6h / CC: ~1h)** — backend-location-endpoints — CRUD `/scenarios/{id}/location`
  + `/location/brief`, validación 422 de marker_x/y en rango y de "marcador sin texto" (B10)
  - Surfaced by: Section 1, B9, B10
  - Files: server/app.py
  - Verify: guardar solo marcador sin texto → 422; marker_x=1.5 → 422
- [ ] **T-BE3 (P1, human: ~4-6h / CC: ~1h)** — backend-scoring-integration — 2 campos nuevos en
  `CriticalDataPoint` (`word_fallback`, `counts_toward_timing`, default True), `_location_critical_points()`,
  fusión incondicional a `all_points` (sin `location_delivered`)
  - Surfaced by: Section 1 (A3, B1, B2, B4, B5, B8 — todos corregidos aquí)
  - Files: core/ports.py, core/scoring.py
  - Verify: transcript con "avenue" suelto NO marca un point con word_fallback=False; puntos de ubicación
    no cambian el resultado de _time_to_critical_data; sesión sin ubicación produce evaluation idéntico
- [ ] **T-BE4 (P2, human: ~3-4h / CC: ~45min)** — migrate-seed-locations — `migrate_seed_locations.py`:
  pre-llena ScenarioLocation desde el CriticalDataPoint ad-hoc existente Y lo retira en el mismo paso
  - Surfaced by: Fase 1 0A-6, Section 2 punto 6 (corregido)
  - Files: persistence/sqlite_scenario_location_store.py, script nuevo
  - Verify: los 3 escenarios semilla quedan con ScenarioLocation Y sin el punto ad-hoc duplicado
- [ ] **T-FE1 (P1, human: ~6-8h / CC: ~1.5-2h)** — location-minimap-component — ver Fase 2 T1 (sin
  cambios: geometría real F17, tokens de Pass 5, teclado F18)
  - Files: frontend/src/components/LocationMiniMap.tsx (nuevo), frontend/src/styles/globals.css
- [ ] **T-FE2 (P1, human: ~6-8h / CC: ~1.5-2h, revisado al alza — B11)** — callpage-gate-sequencing —
  Restructurar `CallPage.tsx` de "1 gate booleano" a una secuencia de 0-2 gates (location, video),
  fetches en paralelo (`Promise.all`, no seriales), UNA sola condición terminal para `call.start` (nunca
  doble-fire), label de botón condicional (F14)
  - Surfaced by: B11 — el hallazgo de mayor riesgo de regresión de toda la revisión; el archivo que hoy
    es dueño exclusivo de cuándo se dispara `call.start`
  - Files: frontend/src/pages/CallPage.tsx, frontend/src/components/PreCallLocationBriefing.tsx (nuevo),
    frontend/src/components/InCallLocationPanel.tsx (nuevo)
  - Verify: escenario con video+location dispara call.start exactamente una vez; escenario con solo uno
    de los dos también; escenario sin ninguno se comporta exactamente igual que hoy
- [ ] **T-FE3 (P1, human: ~3-4h / CC: ~1h)** — editor-location-section — ver Fase 2 T4 (texto primero F3,
  gateado por isEditing F9, Remove location, bloqueo de guardado marcador-sin-texto B10)
  - Files: frontend/src/pages/ScenarioEditorPage.tsx
- [ ] **T-FE4 (P2, human: ~2h / CC: ~30min)** — session-breakdown-location-overlay — SIN estructura de
  datos nueva (corrige B3/B4): `LocationMiniMap mode="review"` colorea verde/gris comprobando membership
  de sus labels en `evaluation.collected`/`missing` ya existentes
  - Files: frontend/src/components/SessionBreakdown.tsx
- [ ] **T-QA1 (P2, human: ~2-3h / CC: ~30min)** — manual-qa-checklist — Los 15 flujos de UI marcados
  `[GAP-QA]` en Section 3, ejecutados manualmente (sin toolchain de frontend, B6) antes de shippear
  - Files: N/A (checklist, alimenta /qa vía el Test Plan Artifact)
```

### Completion Summary — Fase 3 (Eng)
```
  +====================================================================+
  |          ENG PLAN REVIEW — COMPLETION SUMMARY (Fase 3)               |
  +====================================================================+
  | Step 0 (Scope Challenge) | Umbral de complejidad disparado (~19       |
  |                          | archivos, corregido de 10) — NO reducido, |
  |                          | recalculado sobre el número correcto      |
  | Section 1 (Architecture) | 13 hallazgos, 6 CRÍTICO/HIGH — rediseño   |
  |                          | completo de la integración de scoring     |
  | Section 2 (Code Quality) | 7 hallazgos, todos incorporados            |
  | Section 3 (Test Review)  | Diagrama corregido: 19 code paths (pytest)|
  |                          | + 15 flujos de UI (QA manual, sin toolchain)|
  | Section 4 (Performance)  | 1 hallazgo (N+1 de listado, pre-existente,|
  |                          | mitigación diferida a TODOS.md)           |
  +--------------------------------------------------------------------+
  | NOT in scope             | escrito (5 items)                          |
  | What already exists      | escrito                                    |
  | TODOS.md updates         | 3 items nuevos (+ 4 de Fase 1)             |
  | Failure modes            | 0 gaps críticos tras el rediseño (el único |
  |                          | real, location_delivered, fue eliminado)  |
  | Outside voice            | Claude subagent (26 hallazgos) — Codex no |
  |                          | disponible, [subagent-only]                |
  | Parallelization          | 3 lanes (A backend, B minimap, C 3 sub-   |
  |                          | flujos paralelos entre sí)                 |
  | Lake Score                | 8/8 — cada hallazgo crítico/alto se        |
  |                          | corrigió en el diseño, ninguno se difirió |
  |                          | como "implementar y ver"                   |
  +====================================================================+
```

**PHASE 3 COMPLETE.** Codex: no disponible. Claude subagent: 26 hallazgos (5+ CRÍTICO), el más severo de
las tres fases — encontró un exploit de scoring controlado por el cliente (`location_delivered`) y un
bug de fondo en la propia mitigación de 0A-5 (el fallback de palabra suelta). El rediseño resultante es
estrictamente más simple que el borrador original: una clase eliminada, un subsistema completo eliminado,
2 campos booleanos agregados a una clase ya existente. Sin scope DX (no hay superficie developer-facing:
sin API pública, SDK, CLI, ni AI-agent-as-primary-user) — Fase 3.5 se omite. Passing to Phase 4 (Final
Approval Gate).

---

## Decision Audit Trail

Las tablas de decisión detalladas viven inline en cada fase (0D cherry-picks, Fase 2 Pass 7, Fase 3
Sección 2) — esta es la vista consolidada de las decisiones que cambiaron el diseño de fondo, no un
duplicado de cada tabla.

| # | Fase | Decisión | Clasificación | Principio | Rationale | Rechazado |
|---|------|----------|---------------|-----------|-----------|-----------|
| 1 | CEO | Pantalla de pre-llamada (`PreCallLocationBriefing`) pasa de cherry-pick a alcance mínimo | Mecánico | P1 | Sin ella, el ground truth es imposible de cumplir (0A-1) | — |
| 2 | CEO | Un punto combinado en `all_points`, no uno por campo | Mecánico | P4/P5 | Evita re-pesar completeness ~45% en silencio (0A-4) | Uno-por-campo |
| 3 | CEO | Acceso en vivo opt-in (`InCallLocationPanel`) | Mecánico (corregido tras subagente) | P6 | `InCallVideoPanel.tsx` ya existe — el usuario ya revirtió "ocultar todo en vivo" para video | Ocultar por completo (borrador inicial) |
| 4 | Design | Mapa dibuja geometría real (calle+cruce+landmark), no solo un flag flotante | Mecánico | P5 | Sin geometría, el marcador no representa nada (F17) | Flag sin contexto visual |
| 5 | Design | Orden de gates: location → video → call.start | Taste, resuelto por consistencia interna | P5 | Corrige contradicción Fase 1/Fase 2 (F15) | Video → location |
| 6 | Design | Todo el copy de UI en inglés | Mecánico | — | 100% de la UI existente está en inglés (F19) | Español (borrador inicial) |
| 7 | Eng | Eliminar `LocationGroundTruthPoint`, reusar `CriticalDataPoint` + 2 flags nuevos | Mecánico | P4/P8 | Clase idéntica campo-por-campo a una ya existente (B8) | Clase nueva |
| 8 | Eng | Eliminar `location_delivered`/exención de scoring; ubicación se puntúa incondicionalmente, igual que video | Mecánico | P5 | Era un exploit de scoring controlado por el cliente, sin persistencia real (B1/B2) | Exención por "Skip"/fallo de carga |
| 9 | Eng | `word_fallback=False`, `counts_toward_timing=False` en los puntos de ubicación | Mecánico | P1 | Corrige el bug real de A3 (palabra suelta) y B5 (re-peso de timing) | Dejar el fallback activo |
| 10 | Eng | Migración de escenarios semilla retira el punto ad-hoc en el mismo paso que agrega `ScenarioLocation` | Mecánico | P4 | Evita doble conteo del mismo hecho (H2/M1, corregido) | Migración sin retirar el punto viejo |

**Taste decisions que SÍ van al gate (reasonable people podrían discrepar, no se auto-decidieron):**
- **T1 — Categoría "Ubicación" ponderada y visible por separado en el dashboard** (Fase 1, cherry-pick
  #2/0D) vs. mantenerla fusionada dentro de "Completeness" genérico (como quedó diseñado). Es una
  decisión de legibilidad de UI, no de matemática de scoring — ambas opciones muestran los mismos datos
  subyacentes, solo cambia si el supervisor ve una barra "Location" separada o los ve mezclados dentro de
  "Completeness."
- **T2 — Adoptar ahora el reframe de "specificity scoring"** (medir si el trainee dio CUALQUIER ubicación
  accionable, no solo la configurada) **vs. diferir a TODOS.md** (como quedó diseñado, dado que ya se
  resolvió la premisa que lo motivaba — el trainee ahora sí recibe la ubicación configurada, así que
  medir contra ella vuelve a ser válido y es lo que el usuario pidió literalmente).

## Cross-Phase Themes

**Tema 1 — el borrador inicial de cada fase tuvo un error de fondo que la voz independiente encontró, no
un detalle menor:** CEO (premisa de canal de entrega invertida), Design (mapa sin geometría real +
argumento de "ocultar en vivo" ya revertido por el usuario para video), Eng (exploit de scoring
controlado por el cliente + bug de fondo en la propia mitigación de 0A-5). Señal de alta confianza: las
tres correcciones se verificaron contra código real, no fueron opinión — y las tres apuntan a la misma
causa raíz: el borrador inicial razonó desde el precedente de video por analogía en vez de leer el código
de video línea por línea. La voz independiente sí lo leyó, en las tres fases.
**Tema 2 — "básico/ficticio" (petición explícita del usuario) fue mal-interpretado dos veces en
direcciones opuestas:** el borrador de diseño casi lo lee como "sin geometría, un flag decorativo" (F17,
corregido) y el borrador de Eng casi lo sobre-construye con una clase y un subsistema nuevos donde ya
existía uno reutilizable (B8, corregido). El diseño final es más simple que ambos extremos.

## Deferred to TODOS.md (agregado de las 3 fases)

1. RBAC completo (TODO-16, ya trackeado, referenciado no bloqueante).
2. Soporte de múltiples marcadores por escenario (fuera del pedido singular original).
3. `rubric_version` formal en `evaluation` (cross-cutting, afecta también a video).
4. Coordinación con `motor-de-metricas.md` (APPROVED) cuando su LLM-judge se implemente.
5. Verificar contraste de `--muted` sobre `--bg-deep` (mismo TODO que video, T7 relacionado).
6. Toggle "Preview trainee view" en el editor.
7. `list_configured_scenario_ids()` para eliminar el N+1 de listado (pre-existente, mirrorea video).
8. Toolchain de test de frontend (vitest/testing-library) — cross-cutting.
9. `busy_timeout` en los 7 stores SQLite (pre-existente, TODO-20).

## Final Approval Gate

Ver mensaje de chat inmediatamente después de este documento para el gate de aprobación interactivo
(AskUserQuestion) — premisas confirmadas, taste decisions T1/T2, y el resumen ejecutivo completo.
