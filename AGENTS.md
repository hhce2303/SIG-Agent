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

El código en `apps/voice-agent/src/` hoy es el **prototipo original** (CLI, push-to-talk, sin
tests, sin manejo de error) — no la arquitectura de Fase 1 descrita en los ADRs. Antes de
extender ese código directamente, leer [ADR-0006](./docs/architecture/adr/0006-arquitectura-hexagonal.md):
el prototipo sirve como referencia de lógica (parámetros de STT/TTS, system prompt), no como
base a extender tal cual — la revisión de ingeniería documentada en el design doc de origen
detalla exactamente qué sobrevive y qué no.

## Módulos de documentación activos en este repo

- **Hexagonal (sin DDD táctico completo)** — ver [ADR-0006](./docs/architecture/adr/0006-arquitectura-hexagonal.md).
- **arc42** — ver [`docs/architecture/arc42.md`](./docs/architecture/arc42.md).
- **Diagramas C4** — ver [`docs/architecture/c4/`](./docs/architecture/c4/).
- ATAM ligero: no activado en este baseline.
