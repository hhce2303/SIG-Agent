# ADR-0014: Redacción de escenarios asistida por Claude a partir de incidentes, con aprobación humana

- **Status:** accepted — confirmado por el usuario el 2026-09-15, tras investigación con
  `/investigate` + `/codex` en la misma sesión.
- **Date:** 2026-09-15
- **Deciders:** usuario.

## Context and problem statement

El usuario pidió que el sistema "empiece a aprender con el tiempo" usando el SQLite que se
acumula en cada instalación (ver [ADR-0013](./0013-instalador-unificado-monomaquina.md)), de
forma funcional con el LLM de Claude. La API pública de Claude no ofrece fine-tuning (verificado
2026-09-15 vía documentación de Anthropic; AWS Bedrock sí lo ofrece para Claude 3 Haiku, un
producto/integración distinta a los adaptadores `llm/claude.py`/`llm/metrics_judge.py` de este
repo, que usan la Messages API directa). El repo ya tiene un lazo de retroalimentación manual:
`POST /incidents/{id}/promote-to-scenario` crea un `Scenario` vacío de `critical_data_points` a
partir de las notas de un incidente real (`IncidentOutcome.notes`), que el autor completa a mano
en el editor CRUD ya existente (Fase 2).

## Decision drivers

- [GOALS.md](../GOALS.md): Auditabilidad — cualquier salida de Claude que afecte el material de
  entrenamiento debe quedar trazable a una fuente y a una aprobación humana explícita, nunca
  aplicarse sola.
- [TODO-04](../TODOS.md#todo-04): visibilidad self-only + retención de 1 hora de transcripts en
  producción — cualquier memoria/derivado de largo plazo no puede reconstruir esa misma
  información indefinidamente.
- [ADR-0006](./0006-arquitectura-hexagonal.md): el dominio nunca llama a Anthropic ni a SQLite
  directo — cualquier capacidad nueva entra como puerto + adaptador.
- [ADR-0007](./0007-motor-de-persistencia.md) / [ADR-0013](./0013-instalador-unificado-monomaquina.md):
  SQLite embebido, por instalación, sin servidor central — cualquier "aprendizaje" debe funcionar
  con los datos de una sola máquina, no asumir agregación cross-sitio.
- Equipo chico ([TODO-06](../TODOS.md#todo-06)): priorizar la opción de mayor valor con menor
  superficie nueva, no una plataforma de RAG/analítica completa de entrada.

## Considered options

1. RAG/memoria semántica sobre el SQLite local (embeddings + `sqlite-vec`) para dar pocos-shot al
   dispatcher/judge.
2. Extender la promoción manual incidente→escenario para que Claude proponga un borrador completo
   (título, `critical_data_points`, `match_hints`), con un estado de aprobación humana explícita
   antes de publicar.
3. Analítica agregada determinista sobre `evaluation_json` histórico (qué se pierde más seguido,
   qué escenarios/dificultades correlacionan con score bajo).
4. Prompt caching de Anthropic sobre los adaptadores existentes.
5. Exportar/importar paquetes de escenarios/calibración revisados entre instalaciones (agregación
   opt-in, sin sincronizar bases de datos crudas).

## Decision

Se elige la **opción 2** como primer incremento. Es la que mejor encaja con el lazo de feedback
que ya existe, no requiere una colección de ejemplos ya curados (que hoy no existe), no toca el
score determinista (`core/scoring.py::score_session`), y es útil incluso con un solo incidente
bien documentado. Las opciones 1/3/4/5 quedan como follow-ups (ver Consequences), condicionadas a
tener suficiente evidencia revisada o a que el equipo mida que la inversión vale la pena.

Diseño concreto:

- Un incidente sin promover puede pedir un borrador
  (`POST /incidents/{id}/draft-scenario`). Claude (adaptador
  `llm/claude_scenario_drafter.py`, puerto `ScenarioDraftingPort`) propone
  título/categoría/dificultad/idioma/descripción/briefing/`critical_data_points`/`match_hints` y
  una lista de información faltante — nunca inventa un VIN, protocolo policial real, ni marca
  como "confirmado" algo que no esté en `incident.notes`.
- El borrador se guarda en una tabla nueva `scenario_drafts` (adaptador
  `persistence/sqlite_scenario_draft_store.py`, puerto `ScenarioDraftStorePort`) con estado
  `pending`/`approved`/`rejected` — nunca en `scenarios` (mismo principio que
  [TODO-20](../TODOS.md#todo-20): tabla nueva, nunca `ALTER TABLE`).
- Un borrador `pending` es editable (`PUT /scenario-drafts/{id}`) pero no puede iniciar una
  llamada de entrenamiento — no es un `Scenario` real todavía.
- Solo `POST /scenario-drafts/{id}/approve` (gateado a `role == "manager"`, reusando
  `_require_manager` de [ADR-0011](./0011-gate-de-rol-minimo-video-de-incidentes.md)) crea el
  `Scenario` real, marca el borrador `approved` y el incidente `promoted_scenario_id`, en ese
  orden — publicación con orden atómico frente a la falla más probable: si
  `scenario_store.create` falla, ni el borrador ni el incidente cambian de estado (verificado con
  test, `test_approve_scenario_draft_leaves_draft_pending_and_incident_unpromoted_when_scenario_store_create_fails`
  en `test_server_app.py`). Esto NO es una transacción atómica cruzada: `scenario_store`,
  `scenario_draft_store` e `incident_store` son tres conexiones/transacciones SQLite
  independientes (ver ADR-0007), así que una falla en la segunda o tercera llamada
  (`mark_approved`/`mark_promoted`) después de que la primera ya tuvo éxito es un riesgo residual
  real, aunque poco probable, no cubierto por este diseño — quedaría un `Scenario` creado sin que
  el borrador o el incidente lo reflejen todavía. Se acepta ese riesgo residual por ahora (mismo
  criterio de equipo chico que el resto de esta ADR); una transacción cruzada real requeriría un
  motor de persistencia compartido entre los tres stores, fuera de alcance de este incremento.
- `POST /scenario-drafts/{id}/reject` descarta el borrador sin tocar el incidente (se puede
  repetir el draft o promover a mano con el flujo viejo).

## Consequences

**Positive**

- Primer "aprendizaje" reproducible y auditable: incidente real → borrador de Claude → revisión
  humana → escenario usable, sin cambiar pesos de ningún modelo ni introducir dependencias nuevas
  de embeddings.
- Reutiliza puertos existentes (`IncidentOutcomePort`, `ScenarioPort`, `_require_manager`) —
  superficie nueva acotada a 2 puertos + 2 adaptadores + 4 endpoints.
- No compromete TODO-04: el borrador deriva de `incident.notes` (que ya vive indefinidamente por
  diseño, a diferencia de los transcripts de sesión), no de transcripts de llamadas.

**Negative**

- Incidentes con notas pobres producen borradores débiles — el reviewer sigue necesitando
  criterio de dominio, esto no elimina ese trabajo.
- Una llamada nueva a la API de Claude por intento de draft — costo adicional, acotado porque es
  una acción explícita del usuario, no algo que corre en el loop de la llamada en vivo.
- No resuelve "aprendizaje" en el sentido de mejorar el dispatcher/judge en vivo — eso queda para
  las opciones 1/3/4 más adelante.

**Risks**

- `match_hints` generados por Claude pueden introducir falsos positivos/negativos de scoring si
  se aprueban sin revisión real (mismo riesgo que ya existe hoy con `match_hints` escritos a mano
  — TODO-17).
- El `_require_manager` actual valida una passphrase compartida, no una identidad de reviewer
  verificada individualmente — aceptable para este alcance (mismo nivel que ADR-0011), pero no es
  un audit trail de "qué persona aprobó" cada borrador.

## Options not chosen

- **RAG/memoria semántica (1):** la opción de mayor valor a largo plazo para el dispatcher/judge,
  pero requiere una colección de ejemplos ya aprobados que hoy no existe — prematura sin este
  flujo de aprobación primero.
- **Analítica agregada (3):** barata y valiosa, pero depende de un envelope de evaluación
  versionado (`collected`/`missing` hoy son labels, no keys estables) — se revisita una vez que
  ese versionado exista.
- **Prompt caching (4):** optimización de costo independiente, no un mecanismo de aprendizaje —
  se adopta cuando se mida reuso real de contexto; no bloquea esta decisión.
- **Agregación cross-instalación (5):** prematura sin un producto de exportación/importación de
  contenido revisado; fuera de alcance de un equipo chico hoy.
