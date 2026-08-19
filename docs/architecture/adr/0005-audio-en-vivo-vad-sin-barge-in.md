# ADR-0005: Audio en vivo — VAD por turnos, sin barge-in

- **Status:** accepted
- **Date:** 2026-08-19
- **Deciders:** usuario, con revisión CEO/Design/Eng vía `/autoplan`

## Context and problem statement

El prototipo usa push-to-talk (Enter para grabar/parar) — un intercambio por turnos explícito
que no se siente como una llamada real. ¿Qué tan lejos hay que llevar la detección automática de
voz para que la práctica se sienta "en vivo"?

Ver el análisis completo en el design doc de origen:
[`docs/designs/police-call-training-simulator.md`](../../designs/police-call-training-simulator.md#adr-2-arquitectura-de-audio-en-vivo).

## Decision drivers

- Objetivo de calidad #1 (realismo de la interacción en vivo, ver GOALS.md) — pero acotado por
  tiempo/presupuesto de un roadmap de 3 fases.
- Este es, según la propia revisión de premisas, el mayor riesgo técnico de todo el roadmap —
  no un detalle de UI.

## Considered options

1. VAD del lado cliente, sin indicador visual ni plan de barge-in
2. Pipeline streaming completo con barge-in (full-duplex real)
3. VAD por turnos + indicador visual de "quién habla", barge-in diferido

## Decision

Se elige la opción 3. VAD por turnos es el mayor salto de realismo posible (adiós al botón
manual) al costo de ingeniería de la opción 1, sin comprometerse a la complejidad de un pipeline
full-duplex (opción 2) antes de saber si de verdad se necesita. Ir directo a la opción 2 pondría
en juego las 3 fases completas del roadmap por una sola pieza.

## Consequences

**Positive**
- El salto de realismo más grande posible sin el costo de ingeniería de un sistema full-duplex.
- Deja la puerta abierta a agregar barge-in en una fase futura sin haber comprometido una
  arquitectura de streaming completa que podría no hacer falta.

**Negative**
- Sigue sin ser una llamada real al 100% — el supervisor no puede interrumpir al dispatcher
  simulado, lo cual algunos usuarios pueden notar.
- El indicador de turno necesita un modelo de estados completo (escuchando / hablando /
  procesando / recuperación de corte falso / red degradada) — nombrar el indicador no es
  diseñarlo; ver la sección "UI/UX Requirements" del design doc de origen.

**Risks**
- La apuesta de que VAD "se siente más en vivo y entrena mejor" que push-to-talk es, a la fecha
  de este ADR, un argumento de costo de ingeniería, no evidencia de usuario. Mitigación: el
  Gate 0 del roadmap incluye un user-test barato con 2-3 supervisores reales comparando ambos.
- Corte falso de VAD (terminar el turno antes de que el supervisor realmente haya terminado) sin
  un estado de recuperación bien diseñado puede ser peor que push-to-talk para el entrenamiento
  bajo presión — ver TODOS.md.

## Options not chosen

- **Solo VAD, sin indicador (opción 1)**: el cambio más chico posible, pero sin indicador visual
  el supervisor no tiene señal clara de si el sistema lo escuchó o hubo un corte falso — pierde
  buena parte del valor de auditoría de "quién hablaba cuándo".
- **Full-duplex con barge-in (opción 2)**: la versión más fiel a una llamada real, pero es lo
  que le toma meses a un call center real — alto riesgo de que esta única pieza se coma todo el
  roadmap de 3 fases.
