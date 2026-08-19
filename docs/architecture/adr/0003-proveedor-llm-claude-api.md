# ADR-0003: Proveedor de LLM — Claude API (Anthropic), en la nube

- **Status:** accepted
- **Date:** 2026-08-19 (reconstruido — decisión ya en vigor en el prototipo; confirmada explícitamente durante `/office-hours`, ver Premisa 1 del design doc)
- **Deciders:** autor original del prototipo; confirmado con el usuario en sesión de planeación

## Context and problem statement

El "cerebro" del dispatcher simulado necesita un LLM capaz de sostener un roleplay creíble y
en personaje durante una llamada de alta presión. ¿Se usa un proveedor en la nube o un modelo
local?

## Decision drivers

- Calidad de roleplay: el dispatcher debe mantenerse en personaje, hacer las preguntas
  correctas, y no "romper el personaje" — un requisito de calidad de generación alto.
- El prototipo ya integra la API de Claude (`llm/claude.py`) con buenos resultados.
- Concurrencia confirmada = 1 usuario a la vez (ver GOALS.md) — elimina la necesidad de
  infraestructura de batching que justificaría un LLM local.

## Considered options

1. Claude API (Anthropic), en la nube
2. LLM local (Llama, Qwen u otro modelo abierto) corriendo en la misma caja RTX del servidor
3. Híbrido: Claude API con fallback a un LLM local si no hay conectividad

## Decision

Se mantiene Claude API en la nube. Confirmado explícitamente con el usuario: la herramienta
**nunca es 100% offline** — siempre requiere internet para el turno del dispatcher, sin importar
la topología de despliegue elegida (ver [ADR-0004](./0004-topologia-de-despliegue.md)). La
alternativa de LLM local se evaluó y se descartó por ahora: la calidad de roleplay de un modelo
abierto tendría que igualar a Claude, y el salto de ingeniería (evaluación de modelo, sizing de
VRAM, tuning de prompt) no está justificado dado que la conectividad a internet ya es un
requisito asumido del concesionario.

## Consequences

**Positive**
- Mejor calidad de roleplay sin mantener infraestructura de LLM local.
- El RTX del servidor LAN se dedica exclusivamente a acelerar STT+TTS, un problema más acotado.

**Negative**
- Dependencia dura de conectividad a internet y de un proveedor externo — una caída de la API
  de Claude detiene todas las sesiones de entrenamiento.
- El round-trip a Claude es, según la revisión de ingeniería de `/autoplan`, el mayor
  contribuyente probable al presupuesto de latencia (ver [NFR-01](../nfr.md#nfr-01)).

**Risks**
- Si el spike de latencia (Gate 0) muestra que el round-trip a Claude por sí solo rompe el
  presupuesto, la mitigación no es de topología (ADR-0004) sino de streaming de respuesta — ver
  TODOS.md y la sección "Eng/Architecture Requirements" del design doc de origen.

## Options not chosen

- **LLM local en la caja RTX**: eliminaría la dependencia de internet/proveedor externo, pero
  añade evaluación de modelo, sizing de VRAM y tuning de prompt sin evidencia de que la calidad
  de roleplay iguale a Claude — desproporcionado dado que ya se asume conectividad.
- **Híbrido con fallback local**: combina la complejidad de mantener dos rutas de LLM sin que
  ninguna necesidad concreta (uso offline real) lo justifique todavía.
