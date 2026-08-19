# Contribuir a voice-agent

Este repo sigue un modelo de gobierno de decisiones basado en ADRs (Architecture Decision
Records). Esta guía es corta a propósito — si algo no está aquí, probablemente está en
`docs/architecture/AGENTS.md` o en un ADR específico.

## Principios no negociables

1. **ADR-first.** Ninguna decisión estructural (lenguaje, topología de despliegue, estilo
   arquitectónico, motor de persistencia) se implementa sin un ADR aceptado. Si un pedido no
   encaja en las decisiones existentes, se propone un ADR nuevo — nunca se ajusta la
   arquitectura en silencio para que "encaje".
2. **Las decisiones son append-only.** Ciclo de vida de un ADR: `proposed → accepted →
   superseded`. Nunca se borra un ADR. Se marca `superseded by ADR-NNNN` y se conserva el
   registro histórico — la razón detrás de un camino abandonado suele valer más que el camino
   mismo.
3. **Aclarar antes de escribir.** Si el alcance, un nombre, o una decisión es ambiguo, se
   pregunta. Un artefacto plausible construido sobre una suposición incorrecta cuesta mucho
   más deshacer que lo que cuesta preguntar.
4. **Consistencia entre artefactos es obligatoria.** Renombrar un término, agregar un dominio
   nuevo, o cambiar una decisión se propaga a todos los documentos afectados en el mismo
   cambio. Documentación desincronizada es peor que no tener documentación, porque se le
   cree igual.
5. **IDs estables en todas partes.** `ADR-0001`, `NFR-01`, `TODO-01`. Son lo que permite
   referenciar con precisión entre documentos y entre sesiones de trabajo (humanas o de IA)
   que no comparten contexto previo.
6. **Confirmar alcance antes de cambios en cascada.** Renombres o reestructuraciones que tocan
   varios archivos requieren aprobación explícita primero.
7. **Escribir también para consumo de máquina.** Formatos estructurados, invariantes
   explícitos, una sola fuente de verdad por hecho, sin depender de contexto implícito.

## Regla no negociable de la arquitectura hexagonal (ver ADR-0006)

Ninguna dependencia de infraestructura (driver de base de datos, framework HTTP, cliente
WebSocket) entra al núcleo del dominio. El dominio define los puertos (interfaces); los
adaptadores implementan esos puertos contra tecnología real, y ahí viven las preocupaciones de
resiliencia (retries, timeouts, circuit breakers) — nunca en el dominio.

## Convenciones de nombres e IDs

- ADRs: `docs/architecture/adr/NNNN-titulo-corto-en-kebab-case.md`, numeración secuencial de 4
  dígitos, empezando en `0001`. El número es permanente incluso si el ADR queda `superseded`.
- NFRs: `NFR-NN` en `docs/architecture/nfr.md`, un requisito por sección.
- TODOs/decisiones pendientes: `TODO-NN` en `docs/architecture/TODOS.md`, con estado `PENDING`
  / `IN PROGRESS` / `[RESOLVED vX.X]`.
- Términos de dominio: una entrada por término en `docs/architecture/glossary.md` — si el
  código, la conversación, o un documento usan una palabra distinta para lo mismo, es un
  defecto a resolver, no un sinónimo a tolerar.

## Plantilla de ADR

Ver [`docs/architecture/adr/`](./docs/architecture/adr/) para ejemplos ya escritos (ADR-0001 a
ADR-0006). Estructura: Status/Date/Deciders → Context and problem statement → Decision drivers
→ Considered options → Decision → Consequences (positivas, negativas, riesgos) → Options not
chosen. Un ADR con solo consecuencias positivas no evaluó un trade-off, anunció una preferencia.

## Antes de escribir código en `apps/voice-agent/`

Antes de tocar el rewrite de Fase 1 (servidor async, VAD, dominios nuevos), leer:
- [`AGENTS.md`](./AGENTS.md) — punto de entrada para sesiones de IA.
- [`docs/architecture/adr/0006-arquitectura-hexagonal.md`](./docs/architecture/adr/0006-arquitectura-hexagonal.md)
  — el prototipo actual no sobrevive un rewrite tal cual; sirve como referencia de lógica, no
  como base a extender directamente.
- [`docs/architecture/nfr.md`](./docs/architecture/nfr.md) — en particular NFR-02 (recuperación
  en banda) y NFR-10 (tests antes del rewrite).
