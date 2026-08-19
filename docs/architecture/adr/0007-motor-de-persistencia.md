# ADR-0007: Motor de persistencia — SQLite embebido

- **Status:** accepted — confirmado por el usuario el 2026-08-19 (ver
  [TODO-01](../TODOS.md#todo-01)).
- **Date:** 2026-08-19
- **Deciders:** usuario.

## Context and problem statement

El hito de cierre de Fase 1 pide que "la sesión queda registrada" (ver
[roadmap-3-fases.md](../../designs/roadmap-3-fases.md#fase-1)). Hoy no existe ninguna capa de
storage — escenarios, métricas e historial son greenfield. TODO-01 marca esto explícitamente
como "un ADR pendiente de escribir, no un detalle de implementación", así que no se puede
empezar a escribir el adaptador de persistencia sin decidir esto primero.

## Decision drivers

- [NFR-11](../nfr.md#nfr-11) — 1 sesión concurrente, una sola ubicación. No hay caso de uso
  para un motor cliente-servidor separado en Fase 1.
- [ADR-0006](./0006-arquitectura-hexagonal.md) — la persistencia entra como un adaptador detrás
  de un puerto; el dominio no debe notar si el motor es SQLite o Postgres.
- Equipo de 1-2 personas (ver [TODO-06](../TODOS.md#todo-06)) — operar un servidor de base de
  datos separado (Postgres) es costo operativo sin beneficio a este tamaño de despliegue.
- El servidor ya vive en una sola caja RTX (ver [ADR-0004](./0004-topologia-de-despliegue.md))
  — un archivo local es consistente con esa topología, no agrega una dependencia de red nueva.

## Considered options

1. **SQLite embebido** — un archivo en disco en la misma caja RTX, sin proceso de servidor
   separado.
2. **Postgres** — motor cliente-servidor, típicamente en contenedor en la misma LAN.
3. **Almacenamiento en archivos planos** (JSON/NDJSON por sesión, sin motor de query) — lo más
   simple posible.

## Decision

Se elige la opción 1 — SQLite embebido, accedido a través de un puerto `PersistencePort` (ver
[ADR-0006](./0006-arquitectura-hexagonal.md)) para no comprometer el dominio a este motor
específico. Con concurrencia=1 confirmada, ninguna de las razones habituales para elegir
Postgres (múltiples escritores concurrentes, replicación, alta disponibilidad) aplica todavía —
son parte de la contingencia de TODO-14 (revisitar si crece la escala), no del alcance de hoy.
La opción 3 (archivos planos) queda descartada porque el motor de métricas de Fase 2 va a
necesitar queries (filtrar/comparar sesiones en el tiempo) que un formato de archivo plano
obliga a reimplementar a mano.

## Consequences

**Positive**
- Cero infraestructura nueva que operar — consistente con el "dueño operativo de la caja RTX"
  ya siendo el único punto de responsabilidad ([TODO-03](../TODOS.md#todo-03)), sin agregar un
  segundo sistema (base de datos) a mantener.
- Migración a Postgres más adelante es un cambio de adaptador detrás del puerto, no una
  reescritura del dominio — ver ADR-0006.
- Soporta directamente el historial/filtro/comparación de tendencia que pide Fase 2.

**Negative**
- Si la operación crece a más de una ubicación con más de un servidor ([TODO-13](../TODOS.md#todo-13)),
  SQLite por caja implica historiales fragmentados por sitio, no una vista consolidada — se
  revisitaría junto con ADR-0004 en ese escenario.
- Escrituras concurrentes desde más de un proceso son más limitadas que en Postgres — aceptable
  hoy solo porque NFR-11 confirma 1 sesión concurrente.

**Risks**
- Retención de audio/transcripts en un archivo SQLite sin cifrado a nivel de disco puede chocar
  con la política de retención/privacidad todavía no resuelta ([TODO-04](../TODOS.md#todo-04),
  [TODO-05](../TODOS.md#todo-05)) — el esquema debe diseñarse para poder purgar por antigüedad
  una vez que esa política exista, no asumir retención indefinida.

## Options not chosen

- **Postgres (opción 2)**: la elección correcta si el proyecto crece a múltiples ubicaciones o
  necesita alta concurrencia — ver TODO-13/TODO-14. Prematuro para el alcance de una sola caja,
  un usuario a la vez.
- **Archivos planos (opción 3)**: cero dependencias nuevas, pero empuja el costo de indexar y
  filtrar historial a código de aplicación a mano — se vuelve más caro que SQLite apenas Fase 2
  necesita comparar sesiones en el tiempo.
