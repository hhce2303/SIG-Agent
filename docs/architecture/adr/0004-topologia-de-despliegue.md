# ADR-0004: Topología de despliegue — servidor LAN + GPU RTX

- **Status:** accepted — condicionado al resultado del spike de Gate 0 (ver Risks)
- **Date:** 2026-08-19
- **Deciders:** usuario, con revisión CEO/Design/Eng vía `/autoplan`

## Context and problem statement

STT (faster-whisper) y TTS (Kokoro) necesitan correr con latencia baja y consistente para que
una llamada de práctica se sienta en vivo. ¿Dónde corren esos modelos: en la PC de cada
supervisor, o en un servidor centralizado?

Ver el análisis completo de alternativas en el design doc de origen:
[`docs/designs/police-call-training-simulator.md`](../../designs/police-call-training-simulator.md#adr-1-topología-de-despliegue).

## Decision drivers

- [NFR-01](../nfr.md#nfr-01) — latencia end-to-end <1.5s, ideal <800ms.
- Concurrencia confirmada = 1 usuario, una sola ubicación (ver GOALS.md) — simplifica el
  dimensionamiento de cualquier servidor central.
- El riesgo de que el rendimiento varíe según el hardware de cada PC de supervisor amenaza
  directamente el objetivo de calidad #1 (realismo de la interacción en vivo).

## Considered options

1. Ejecutable standalone por PC (STT/TTS locales en cada máquina de supervisor)
2. Servidor LAN con RTX + cliente Electron liviano (FastAPI/WebSocket)
3. Híbrido: local-primero con fallback transparente a LAN

## Decision

Se elige la opción 2 — servidor LAN con RTX. Con concurrencia=1 y una sola ubicación
confirmadas, el costo de mantener una sola caja es bajo, y este es un entrenamiento de una
habilidad crítica bajo presión: el riesgo de que la opción 1 se sienta "lenta" en una laptop de
oficina amenaza directamente la razón de ser del producto. La opción 3 queda descartada por
ahora — más ingeniería que las otras dos sin evidencia de que el parque de PCs sea disparejo o
de que se necesite entrenamiento remoto.

## Consequences

**Positive**
- Rendimiento garantizado y consistente, independiente del hardware de cada supervisor.
- Un solo lugar para actualizar modelos y escenarios.
- El cliente que se distribuye a cada PC es mínimo.

**Negative**
- Alguien debe ser dueño operativo de la caja (parches, uptime) — sin dueño nombrado, este tipo
  de pieza suele estancarse en revisión de IT/seguridad (ver TODOS.md).
- La LAN se vuelve una dependencia dura: si el servidor cae, nadie entrena. Mitigación mínima:
  el prototipo CLI actual se mantiene como fallback manual mientras el servidor madura.
- Hay que construir un protocolo de audio-por-red (jitter, pérdida de paquetes, reconexión) —
  riesgo del mismo orden que VAD (ver [ADR-0005](./0005-audio-en-vivo-vad-sin-barge-in.md)).
- Superficie de ataque nueva: un servidor WebSocket+GPU siempre encendido en la LAN de oficina.
  Requiere auth por sesión y WSS/TLS como gate de Fase 1, no como mejora posterior.

**Risks**
- **Esta decisión está condicionada al spike de Gate 0** (medir latencia end-to-end real,
  incluyendo el round-trip a Claude, en la caja RTX vs. una laptop típica, y probar la conexión
  sobre la LAN real con dos máquinas). Si el spike muestra que el hardware típico de un
  supervisor ya cumple el objetivo de latencia corriendo todo local, esta decisión se reevalúa
  a favor de la opción 1.
- Mecanismo de autenticación y dueño operativo siguen sin resolver — ver TODOS.md.

## Options not chosen

- **Ejecutable standalone (opción 1)**: la opción más simple de lanzar (cero infraestructura
  compartida), pero el rendimiento depende del hardware de cada PC — riesgo directo sobre el
  objetivo de calidad #1. Queda como opción de respaldo si el spike de Gate 0 invalida la
  opción elegida.
- **Híbrido local + fallback LAN (opción 3)**: la más flexible, pero también la más cara de
  construir y mantener (dos rutas de código) — prematura sin evidencia de que se necesite.
