# ADR-0010: Mecanismo de comparación para scoring de ground truth de video

- **Status:** accepted — resuelto en la misma sesión de implementación de
  [escenarios-de-video.md](../../designs/escenarios-de-video.md), sin bloquear en espera de un
  análisis de costo/latencia separado, según instrucción explícita del usuario.
- **Date:** 2026-08-21
- **Deciders:** implementación directa (Claude Code), sobre un hallazgo que dos voces
  independientes de `/autoplan` (CEO y Eng) marcaron como bloqueante duro: no reproducir la falla
  ya medida de TODO-17 sobre una superficie de scoring nueva.

## Context and problem statement

Los escenarios de video necesitan puntuar qué tan completo fue el reporte del entrenando contra
el "ground truth" de lo que el video muestra (`VideoGroundTruthPoint`). TODO-17 ya documentó, con
una llamada real, que comparar por keyword-matching literal del `label` de un dato contra el
transcript falla catastróficamente (17/100 en un reporte perfecto) porque el label es una etiqueta
de UI, no vocabulario real. El fix de TODO-17 en esta misma sesión agregó `match_hints` —frases de
contenido autoradas por quien crea el escenario— a `CriticalDataPoint` y al comparador
`core/scoring.py::_matches_point`. La pregunta para ground truth de video es si reusar ese mismo
mecanismo (extendido con hints) alcanza, o si hace falta la "mejora natural" que el propio
docstring de `scoring.py` ya nombraba desde antes: extracción semántica vía LLM.

## Decision drivers

- No repetir la falla medida de TODO-17 sobre una superficie nueva y de mayor costo emocional
  (el entrenando ya vio el video — un "no lo mencionaste" incorrecto pesa más que en un escenario
  de texto).
- Evitar una llamada nueva a Claude por sesión sin evidencia de que la heurística de hints no
  alcance — mismo argumento de costo/latencia que ya se aplicó al fix de TODO-17 para escenarios
  de texto (docstring de `core/scoring.py`).
- Consistencia: usar el mismo mecanismo para texto y video simplifica el código y el modelo
  mental de quien autora escenarios (una sola forma de "match_hints" que aprender).

## Considered options

1. **Reusar `_matches_point` con `match_hints`, extendido a `VideoGroundTruthPoint`** — sin
   dependencia nueva, mismo mecanismo que el fix de TODO-17 para texto.
2. **Extracción semántica vía LLM** (una llamada a Claude al final de la sesión, comparando el
   transcript completo contra la lista de ground truth) — mayor costo/latencia, no determinístico,
   requiere su propio análisis (el que TODO-17 nunca llegó a hacer).
3. **No puntuar cobertura de video en absoluto** (solo mostrar el score existente de hoy) —
   contradice directamente el pedido del usuario.

## Decision

Se elige la opción 1: extender `VideoGroundTruthPoint` con `match_hints` (mismo campo, mismo
comparador `_matches_point`, ver `core/scoring.py::_video_completeness`), en vez de introducir
una extracción por LLM todavía. Esto no es "la heurística de siempre reciclada sin pensar" — es
la misma heurística *después* del fix de TODO-17, que ataca exactamente la causa raíz que hacía
fallar el matching literal (label ≠ vocabulario real). La opción 2 queda como mejora natural
documentada, no descartada: si en uso real los `match_hints` resultan insuficientes para hechos
de video más abiertos ("el sospechoso llevaba una campera roja" tiene más formas válidas de
decirse que "License plate"), ahí sí vale la pena el análisis de costo/latencia de una llamada a
Claude — pero no hay evidencia todavía de que haga falta, y construirlo sin esa evidencia sería
exactamente la "solución elegante prematura" que el docstring original de `scoring.py` ya advertía
evitar.

## Consequences

**Positive**
- Cero costo/latencia adicional por sesión (no hay una segunda llamada a Claude).
- Mismo mecanismo, mismo modelo mental, para quien autora escenarios de texto o de video.
- No reproduce la falla medida de TODO-17 — los hints, no el label, son lo que se compara.

**Negative**
- Sigue siendo una heurística determinista, no comprensión semántica real — un entrenando que
  describe algo con vocabulario que nadie anticipó en los hints puede seguir recibiendo un falso
  negativo. Mitigación parcial: la autoría de escenarios de video (paso 3.5 del roadmap de
  implementación) debe tratar `match_hints` como campo obligatorio, no opcional, y con múltiples
  sinónimos por punto, no solo uno.
- Ground truth de video tiene naturalmente más superficie de hechos por escenario que los ~4-6
  `critical_data_points` de un escenario de texto — más puntos significa más oportunidades de un
  hint mal elegido. Se compensa con la obligatoriedad de hints arriba, no con código adicional.

**Risks**
- Si el uso real muestra una tasa alta de falsos negativos incluso con hints bien autorados
  (evidencia real, no anticipada), la opción 2 (LLM) pasa de "mejora futura documentada" a
  "siguiente prioridad" — este ADR no cierra esa puerta, la deja explícitamente abierta.

## Options not chosen

- **Extracción por LLM (opción 2)**: la mejora "correcta" a largo plazo si la heurística de hints
  resulta insuficiente en uso real — no descartada, diferida hasta tener esa evidencia.
- **No puntuar cobertura de video (opción 3)**: descartada, contradice el pedido explícito del
  usuario y el objetivo mismo de esta feature.
