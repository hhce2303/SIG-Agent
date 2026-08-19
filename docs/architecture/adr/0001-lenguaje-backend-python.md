# ADR-0001: Lenguaje/runtime del backend — Python

- **Status:** accepted
- **Date:** 2026-08-19 (reconstruido — la decisión ya estaba en vigor antes de este baseline)
- **Deciders:** autor original del prototipo

## Context and problem statement

El backend necesita hablar con tres piezas del ecosistema de IA de voz: transcripción (STT),
síntesis de voz (TTS) y un cliente de LLM. ¿En qué lenguaje se implementa?

## Decision drivers

- El ecosistema de STT/TTS local (faster-whisper, Kokoro) es nativo de Python — usar otro
  lenguaje implicaría bindings o llamar a un sidecar de todos modos.
- El prototipo ya existía en Python antes de esta sesión de planeación; reescribirlo en otro
  lenguaje no tiene ningún driver de calidad que lo justifique.

## Considered options

1. Python
2. Node.js/TypeScript (compartiría lenguaje con el cliente Electron/React)
3. Go (para el servidor async de alto rendimiento)

## Decision

Se mantiene Python, porque es la razón real por la que el prototipo ya está escrito así: el
ecosistema de modelos de voz (faster-whisper, Kokoro) es Python-first, y no hay ningún driver
de calidad (rendimiento, equipo, despliegue) que compense reescribir esa capa en otro lenguaje.

## Consequences

**Positive**
- Cero fricción para reusar `stt/whisper.py`, `tts/kokoro.py`, `llm/claude.py` como referencia
  de lógica del nuevo backend (ver [ADR-0006](./0006-arquitectura-hexagonal.md)).
- Ecosistema maduro de librerías de IA/ML si el proyecto necesita evolucionar el pipeline.

**Negative**
- Dos lenguajes en el stack (Python backend, TypeScript/React cliente) — sin código ni tipos
  compartidos entre cliente y servidor.
- El manejo de concurrencia async en Python (necesario para el servidor WebSocket, ver
  [ADR-0004](./0004-topologia-de-despliegue.md)) es más verboso que en runtimes construidos
  async-first.

**Risks**
- Si el proyecto creciera a necesitar alta concurrencia (hoy explícitamente fuera de alcance,
  ver GOALS.md), esta decisión debería revisitarse — ver TODOS.md.

## Options not chosen

- **Node.js/TypeScript**: unificaría el lenguaje con el cliente, pero obligaría a llamar a
  faster-whisper/Kokoro vía bindings nativos o un sidecar Python de todos modos — no elimina la
  dependencia de Python, solo la esconde.
- **Go**: mejor concurrencia nativa, pero sin ecosistema STT/TTS local maduro — el mismo
  problema que Node.js, sin la ventaja de compartir lenguaje con el cliente.
