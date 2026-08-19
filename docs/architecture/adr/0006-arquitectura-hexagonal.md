# ADR-0006: Estilo arquitectónico del backend — hexagonal (puertos/adaptadores), sin DDD táctico completo

- **Status:** accepted
- **Date:** 2026-08-19
- **Deciders:** usuario, durante la entrevista de `/architecture-bootstrap`

## Context and problem statement

El backend actual (`apps/voice-agent/src/`) ya tiene una separación implícita en módulos
intercambiables (STT, TTS, LLM), pero también tiene cero manejo de error, cero tests, y va a
crecer con dominios nuevos (escenarios, métricas, historial) sobre una reescritura async
significativa (ver [ADR-0004](./0004-topologia-de-despliegue.md)). ¿Qué tanta estructura
arquitectónica formal vale la pena imponer antes de esa reescritura?

## Decision drivers

- Objetivo de calidad #5 (mantenibilidad, ver GOALS.md) — bus factor de 1 persona, cero tests
  hoy.
- Las clases actuales (`WhisperSTT`, `KokoroTTS`, `ClaudeDispatcher`) ya están escritas como
  adaptadores intercambiables en la práctica, aunque no formalizados como puertos.
- Equipo chico (1-2 personas) y alcance de una sola ubicación — DDD táctico completo (agregados,
  value objects, bounded contexts formales) es ceremonia costosa para ese tamaño de equipo.

## Considered options

1. DDD + hexagonal completo (bounded contexts formales, agregados, value objects, lenguaje
   ubicuo normativo)
2. Solo hexagonal — puertos y adaptadores, sin el aparato táctico de DDD
3. Sin arquitectura formal — mantener el estilo actual (módulos ad-hoc importados directamente)

## Decision

Se elige la opción 2. STT/TTS/LLM ya están escritos como clases intercambiables — formalizar
eso como puertos/adaptadores es casi gratis y sigue un patrón que el código ya insinúa. DDD
táctico completo (agregados, value objects, bounded contexts) es más ceremonia de la que un
equipo de 1-2 personas necesita para el alcance actual (una sola ubicación, cuatro dominios de
producto de tamaño moderado). Si el proyecto crece en complejidad de dominio o en equipo, esta
decisión debe revisitarse — no se descarta DDD táctico para siempre, se descarta para el alcance
de hoy.

## Consequences

**Positive**
- El dominio (turnos de llamada, escenarios, sesiones, métricas) no depende de FastAPI,
  WebSockets, ni de qué motor de persistencia se elija (ver TODOS.md) — se puede cambiar
  infraestructura sin tocar la lógica de negocio.
- Los adaptadores (STT, TTS, LLM, futura persistencia) son el lugar correcto para las
  preocupaciones de resiliencia (retries, timeouts, circuit breakers) que la revisión de
  ingeniería de `/autoplan` marcó como ausentes hoy — esto les da un hogar arquitectónico
  explícito, no solo un "hay que agregar manejo de error" suelto.
- Migración incremental: los módulos actuales se pueden envolver como adaptadores sin
  reescribir su lógica interna.

**Negative**
- Una capa de indirección (puertos) que no existía antes — cualquier cambio a un adaptador
  requiere respetar el contrato del puerto, no solo cambiar la implementación.
- Sin bounded contexts formales, "escenario", "sesión" y "métrica" comparten un solo modelo de
  lenguaje ubicuo (ver `glossary.md`) — si el dominio crece y esos términos empiezan a
  significar cosas distintas en contextos distintos, esta decisión debe revisitarse.

**Risks**
- La regla no negociable de hexagonal — "ninguna dependencia de infraestructura entra al núcleo
  del dominio" — es fácil de violar bajo presión de tiempo (ej. importar el driver de base de
  datos directo en la lógica de turnos). Debe quedar como regla explícita en `CONTRIBUTING.md`.

## Options not chosen

- **DDD + hexagonal completo (opción 1)**: justificable si el equipo o la complejidad de dominio
  crecen (más de una ubicación, más tipos de incidente, reglas de negocio que varíen por
  cliente) — pero hoy sería indirección sin beneficio claro, dado el tamaño del equipo y el
  alcance de una sola ubicación.
- **Sin arquitectura formal (opción 3)**: es lo que el código tiene hoy, y es exactamente lo que
  la revisión de ingeniería de `/autoplan` señaló como no sobreviviente al rewrite hacia
  cliente-servidor + nuevos dominios — mantenerlo así solo pospone el costo, no lo elimina.
