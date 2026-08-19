# AGENTS.md — punto de entrada para sesiones de IA

Este archivo es para un agente de IA (o una persona) que entra a este repo sin contexto previo.
No duplica contenido — enlaza a la fuente de verdad de cada tema. Si algo aquí contradice el
documento enlazado, el documento enlazado gana.

## Orden de lectura obligatorio

1. [`docs/architecture/GOALS.md`](./docs/architecture/GOALS.md) — qué es este proyecto, para
   quién, y qué objetivos de calidad priorizan sobre cuáles.
2. [`docs/architecture/glossary.md`](./docs/architecture/glossary.md) — vocabulario de dominio.
   Usar estos términos exactamente, no sinónimos.
3. [`docs/architecture/adr/`](./docs/architecture/adr/) — las 6 decisiones estructurales
   vigentes (ADR-0001 a ADR-0006), en orden.
4. [`docs/architecture/nfr.md`](./docs/architecture/nfr.md) — requisitos de calidad con ID
   estable, referenciados desde los ADRs y desde este archivo.
5. [`docs/architecture/TODOS.md`](./docs/architecture/TODOS.md) — decisiones pendientes y
   riesgos conocidos. Antes de asumir algo no resuelto, revisar si ya está aquí como TODO.
6. [`CONTRIBUTING.md`](./CONTRIBUTING.md) — principios no negociables, plantilla de ADR,
   convenciones de nombres/IDs.
7. [`docs/designs/police-call-training-simulator.md`](./docs/designs/police-call-training-simulator.md)
   y [`docs/designs/roadmap-3-fases.md`](./docs/designs/roadmap-3-fases.md) — el análisis
   completo de producto/premisas y el roadmap de 3 fases que originó los ADRs de este baseline.
8. [`docs/architecture/PHASE1-PROGRESS.md`](./docs/architecture/PHASE1-PROGRESS.md) — estado
   real de cada ítem del checklist de cierre de Fase 1 (DONE/IN PROGRESS/BLOCKED), para no
   volver a explorar el código desde cero cada sesión.

## Reglas arquitectónicas no negociables

| # | Regla | Fuente de verdad |
|---|---|---|
| 1 | Ninguna decisión estructural se implementa sin un ADR aceptado. | [CONTRIBUTING.md](./CONTRIBUTING.md) |
| 2 | El dominio nunca importa infraestructura (DB, HTTP, WebSocket) directamente — solo a través de puertos. | [ADR-0006](./docs/architecture/adr/0006-arquitectura-hexagonal.md) |
| 3 | El sistema nunca es 100% offline — el LLM (Claude API) siempre requiere conectividad. | [ADR-0003](./docs/architecture/adr/0003-proveedor-llm-claude-api.md) |
| 4 | Ningún error de la API de Claude, corte de VAD, o caída de red puede fallar en silencio — todo error tiene un estado de recuperación definido. | [NFR-02](./docs/architecture/nfr.md#nfr-02) |
| 5 | No se fusiona código de servidor sin mecanismo de auth por sesión y WSS/TLS. | [NFR-04](./docs/architecture/nfr.md#nfr-04), [NFR-05](./docs/architecture/nfr.md#nfr-05) |
| 6 | El harness de tests se construye antes del rewrite de VAD/servidor, no después. | [NFR-10](./docs/architecture/nfr.md#nfr-10) |
| 7 | El sistema está dimensionado para 1 sesión concurrente, una sola ubicación — no escalar esto implícitamente. | [NFR-11](./docs/architecture/nfr.md#nfr-11) |
| 8 | Nunca se borra un ADR ni un TODO — se marca `superseded` o `[RESOLVED vX.X]`. | [CONTRIBUTING.md](./CONTRIBUTING.md) |

## Estado del código vs. la documentación (importante)

El código en `apps/voice-agent/src/` sigue siendo el **CLI push-to-talk del prototipo original**
como punto de entrada (`main.py`) — no el servidor async/VAD de Fase 1. Lo que sí cambió desde
el baseline original: el prototipo ya tiene puertos formales (`core/ports.py`, ADR-0006), manejo
de error de Claude como estado de primera clase (reintento + recuperación en diálogo, NFR-02),
adaptadores de persistencia (SQLite, ADR-0007) y auth (token propio, ADR-0008), una máquina de
estados de turno completa (`core/turn_state.py`), **y ahora también un servidor FastAPI/
WebSocket real** (`server/app.py` + `server_main.py`) que cablea todo lo anterior — login,
handshake autenticado con scope por sesión, sincronización de eventos de turno, registro de
sesión al desconectar. Lo que ese servidor todavía NO tiene: el pipeline de audio real
(VAD/chunks — a propósito, ver PHASE1-PROGRESS.md) y WSS/TLS. Harness de tests real, 42 tests,
ver `pytest.ini`. Ver [`PHASE1-PROGRESS.md`](./docs/architecture/PHASE1-PROGRESS.md) para el
detalle ítem por ítem.
Antes de extender este código, leer [ADR-0006](./docs/architecture/adr/0006-arquitectura-hexagonal.md):
sigue siendo referencia de lógica de dominio (parámetros de STT/TTS, system prompt), no la base
del servidor de Fase 1 — el core async/WebSocket todavía no existe.

## Módulos de documentación activos en este repo

- **Hexagonal (sin DDD táctico completo)** — ver [ADR-0006](./docs/architecture/adr/0006-arquitectura-hexagonal.md).
- **arc42** — ver [`docs/architecture/arc42.md`](./docs/architecture/arc42.md).
- **Diagramas C4** — ver [`docs/architecture/c4/`](./docs/architecture/c4/).
- ATAM ligero: no activado en este baseline.
