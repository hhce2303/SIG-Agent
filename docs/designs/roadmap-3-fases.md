# Roadmap: Simulador de llamadas en vivo para entrenamiento de supervisores

Generado el 2026-08-19, a partir de la sesión de `/office-hours` + `/autoplan` sobre
[police-call-training-simulator.md](./police-call-training-simulator.md) (design doc de
referencia — ahí están las premisas completas, los dos ADRs y los 36 hallazgos de la revisión
cruzada CEO/Design/Eng, todos ya incorporados).

**Meta del roadmap:** llegar al punto en que un supervisor en entrenamiento sostenga una llamada
completa en tiempo real (sin push-to-talk) contra un escenario configurable, y que esa sesión se
audite después con métricas objetivas.

**Confirmado antes de este roadmap:** build en casa (no buy), una sola ubicación/concesionario
(ADR-1/B se mantiene sin multiplicarse por sitio).

---

## Fase 0 — Spike de validación (gate, no fase de producto)

Antes de escribir código de Fase 1: esto es "The Assignment" del design doc, y es la puerta de
entrada a todo lo demás — nada de Fase 1 se construye sobre una arquitectura sin validar.

- **Spike de latencia end-to-end**: correr el loop completo STT → Claude API → TTS en la caja
  RTX candidata y en una laptop de oficina típica, midiendo latencia real (objetivo <1.5s,
  ideal <800ms).
- **Spike de red real**: repetir la medición con un cliente Electron en una PC separada
  conectada a la caja RTX por la LAN real (no localhost), anotando jitter/cortes.
- **User test barato de turno**: 2-3 supervisores reales prueban push-to-talk actual vs. un
  prototipo simple de VAD, para tener evidencia (no solo argumento de costo de ingeniería) de
  que ADR-2 vale la pena.
- **Clasificación de causa raíz** del/los incidente(s) documentado(s) que motivaron el proyecto
  (¿pánico/habla, falta de datos a la mano, no saber a quién llamar, protocolo?) — informa qué
  entrena realmente el simulador.
- **Salida de este gate**: confirma o ajusta ADR-1 (servidor LAN vs. standalone) y ADR-2 (VAD
  por turnos vale la pena), y re-confirma con el jefe de área la arquitectura específica
  elegida — no solo el concepto que ya vio en el CLI.

---

## Fase 1 — El loop de llamada en vivo, como producto real

**Objetivo de la fase:** un supervisor sostiene una llamada completa en tiempo real (sin botón),
en la arquitectura que el spike validó, con manejo de error real y una red de seguridad de
tests — sin esto todavía no hay "producto real", solo una demo más grande.

**Backend / arquitectura**
- Core async de servidor (FastAPI/WebSocket) + pipeline de audio de cliente Electron — tratado
  como reescritura nueva, no como adaptar el prototipo (ver Eng/Architecture Requirements en el
  design doc).
- State machine de turnos explícito: listening / supervisor-hablando / procesando (con timeout
  y fallback) / dispatcher-hablando / recuperación-de-corte-falso / red-degradada /
  desconectado. Reloj del servidor como autoridad única para métricas de tiempo.
- Manejo de error de Claude API como estado de primera clase (timeout, retry acotado,
  recuperación en el propio diálogo — ej. "¿puede repetir eso?").
- Confianza de STT expuesta por segmento + confirmación explícita de datos críticos
  (placa/VIN) en el system prompt del dispatcher.
- Mecanismo de autenticación decidido + token de sesión con scope por supervisor + WSS/TLS —
  **gate de seguridad: no se fusiona código de servidor sin esto.**
- Logging estructurado con id de correlación por sesión/turno, y latencia por turno guardada
  desde el día uno.
- Harness de tests real ANTES de tocar el rewrite: unit tests de STT/TTS/LLM con I/O mockeado
  (incluyendo un fixture de "VIN poco claro"), test de integración con Claude stub, test de
  caos que inyecte un error de Claude a medio turno. Incluye corregir el bug ya existente de
  `test_microphone.py` (llama a un parámetro `duration` que `MicrophoneRecorder.record()` no
  acepta).

**Frontend (Electron + React + Tailwind)**
- Pantalla de llamada con el indicador visual de turno con todos sus estados (no solo
  "quién habla" — incluye "procesando" y "recuperación de corte falso", para no dejar pantalla
  muerta durante el round-trip a Claude).
- Estado de conexión/reconexión visible (la caída de LAN es riesgo del mismo orden que VAD).
- Control de pausa/abortar la práctica + qué pasa con una sesión incompleta.
- Transición de decompresión entre el fin de la llamada y la pantalla de resultado (evitar el
  corte instantáneo a un score, que puede sentirse punitivo).
- Escenarios: mecanismo de escenario intercambiable con datos estructurados (no la única opción
  hardcodeada de hoy), pero **sin el editor completo de escenarios todavía** — eso se resuelve
  en Fase 2, una vez definido el formato (campos guiados vs. texto libre).
- El prototipo CLI actual se mantiene funcional como fallback manual mientras el servidor LAN
  madura — un supervisor siempre tiene algo con qué entrenar aunque el servidor no esté listo.

**Organizacional (bloqueante, no técnico)**
- Dueño operativo nombrado para la caja RTX y para el mecanismo de auth.
- Política de retención/privacidad del historial resuelta (¿quién ve qué — el propio
  supervisor, su jefe, RRHH?) — sin esto, los supervisores no van a practicar honestamente.
- Presupuesto de capital para la GPU confirmado, separado del presupuesto de tiempo ya
  asignado.
- Segundo ingeniero/revisor nombrado — empieza por el harness de tests, antes del rewrite.

**Hito de cierre de Fase 1:** un supervisor sostiene una llamada de práctica completa en tiempo
real contra un escenario configurable (sin editor de UI todavía), con manejo de error real, y la
sesión queda registrada — sin puntaje/ponderado todavía, eso es Fase 2.

---

## Fase 2 — Los dominios de producto completos: escenarios, métricas, historial

**Objetivo de la fase:** cerrar los 3 dominios que quedaron bloqueados en Fase 1 por preguntas
abiertas, ahora que esas preguntas tienen dueño y fecha.

- **Editor de escenarios**: resolver primero el formato (campos estructurados guiados vs. texto
  libre tipo el `SCENARIO` actual) — la respuesta determina si esto es un formulario validado o
  un editor de texto/plantillas, son problemas de UI distintos. Luego construir CRUD completo,
  con más de un tipo de incidente además de robo de vehículo.
- **Motor de métricas/ponderado**: resolver primero la fórmula (peso de tiempo-hasta-dato-crítico
  vs. completitud vs. claridad/muletillas vs. tiempo total). Luego la pantalla: puntaje
  compuesto, desglose, y narrativa de debrief — son 3-4 pantallas distintas, no una.
- **Historial de sesiones**: implementar la política de retención/visibilidad ya resuelta en
  Fase 1 (organizacional) como el modelo de visibilidad real de esta pantalla — lista/filtro,
  posible replay, comparación de tendencia en el tiempo.
- **Ajustes**: la pieza más chica, alcance mínimo (voz de TTS, sensibilidad de VAD si aplica).
- **Pulido del loop en vivo**: control de pausa/abortar con puntaje diferenciado (abandono
  deliberado vs. caída de red), estado de "conectando/chequeo de mic" antes de iniciar llamada.
- **Si el spike de Fase 0 mostró que el round-trip a Claude solo ya rompe el presupuesto de
  latencia**: integrar aquí el pipeline de streaming (tokens de Claude → síntesis incremental de
  Kokoro → audio en chunks) como workstream propio, no como nota al pie.

**Hito de cierre de Fase 2:** el ciclo completo que pide el `/goal` original — llamada en vivo +
escenario elegido por el usuario + auditoría con métricas objetivas al terminar — funciona de
punta a punta.

---

## Fase 3 — Cierre del lazo de impacto real + robustecimiento

**Objetivo de la fase:** pasar de "la herramienta funciona" a "la herramienta mejora las
llamadas reales" — y endurecer lo que quedó deliberadamente diferido en fases anteriores.

- **Métrica de resultado real**: correlacionar desempeño de supervisores entrenados vs. no
  entrenados en incidentes reales — sin esto, la herramienta puede tener 100% de uso y 0% de
  impacto medible.
- **Lazo de retroalimentación**: que los post-mortems de incidentes reales alimenten la librería
  de escenarios (cerrar el círculo entre "por qué se construyó esto" y "qué se practica").
- **Barge-in / full-duplex** (ADR-2 lo dejó fuera deliberadamente) — revisitar solo si la
  evidencia de Fase 0-2 muestra que el entrenamiento lo necesita, no por defecto.
- **Auto-update del cliente Electron.**
- **Híbrido local + fallback LAN** (Approach C de ADR-1, descartada por ahora) — solo si
  entrenamiento remoto/WFH se vuelve un caso real.
- **Si la operación crece a más de una ubicación**: revisar si ADR-1/B sigue siendo la elección
  correcta o si el costo de replicar servidor+dueño+auth por sitio inclina hacia el ejecutable
  standalone en los sitios nuevos.
- Integración de auth con SSO corporativo si no se resolvió ya en Fase 1.

---

## Qué NO está en este roadmap (a propósito)

- Soporte bilingüe (el entrenamiento es en inglés, como el prototipo actual — no se pidió).
- Escalar a múltiples usuarios concurrentes (concurrencia=1 confirmada).
- Evaluar plataformas comerciales de roleplay/línea telefónica (ya descartado antes de esta
  sesión — build, no buy).

## Referencias

- Design doc completo con premisas, ADRs y los 36 hallazgos de revisión:
  [police-call-training-simulator.md](./police-call-training-simulator.md)
