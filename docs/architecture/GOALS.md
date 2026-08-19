# GOALS — voice-agent

## Propósito

`voice-agent` entrena a supervisores de concesionarios de vehículos (USA) a comunicar reportes
de robo/incidentes a la policía con claridad y rapidez, mediante llamadas de práctica en tiempo
real contra un dispatcher policial simulado por IA — auditadas después con métricas objetivas.

No existía ninguna herramienta interna para esto antes de este proyecto; los supervisores
practicaban (si acaso) en llamadas reales, sin margen de error. Ver el design doc de origen:
[`docs/designs/police-call-training-simulator.md`](../designs/police-call-training-simulator.md).

## Objetivos de calidad (priorizados)

1. **Realismo de la interacción en vivo.** Latencia end-to-end <1.5s (ideal <800ms, ver
   [NFR-01](./nfr.md#nfr-01)), turnos detectados automáticamente (sin botón). Sin esto no hay
   entrenamiento real — es la razón de ser del producto (ver [ADR-0005](./adr/0005-audio-en-vivo-vad-sin-barge-in.md)).
2. **Confiabilidad del ciclo de llamada.** Una sesión no debe fallar en silencio: errores de la
   API de Claude, cortes de VAD y caídas de red necesitan un estado de recuperación definido, no
   un cuelgue.
3. **Auditabilidad.** Cada sesión produce un historial trazable y un score objetivo — sin esto,
   "se practicó" no se puede distinguir de "se entrenó de verdad".
4. **Confianza del espacio de práctica.** Si un supervisor cree que su jefe o RRHH puede ver sus
   fallos de práctica sin reglas claras, deja de practicar honestamente — la política de
   retención/visibilidad es tan objetivo de calidad como cualquier NFR técnico.
5. **Mantenibilidad.** El proyecto hoy tiene bus factor de 1 persona y cero tests — cualquier
   decisión de arquitectura debe dejar el código más fácil de modificar con seguridad, no más
   frágil.

## Stakeholders y expectativas

| Stakeholder | Expectativa |
|---|---|
| Supervisores (usuarios finales) | Una práctica que se sienta real, sin fricción técnica, en un espacio donde equivocarse es seguro. |
| Jefe de área (sponsor) | Una herramienta real, no un demo — pero sin comprometer presupuesto/tiempo por apuestas de ingeniería no validadas. |
| IT / seguridad (dueño futuro del servidor) | Un servidor LAN con auth y superficie de ataque acotada, no una caja sin dueño. |
| Segundo ingeniero (a nombrar, ver TODOS.md) | Código con tests y arquitectura legible, no un prototipo de una sola persona sin red de seguridad. |
| RRHH / legal (implícito) | Política de privacidad de grabaciones de empleados clara antes de almacenar audio real (ver TODOS.md — sin restricción regulatoria confirmada todavía). |

## Alcance confirmado

- Una sola ubicación/concesionario (no multi-sitio) — ver [ADR-0004](./adr/0004-topologia-de-despliegue.md).
- 1 usuario entrenando a la vez (sin concurrencia).
- Entrenamiento y evaluación en inglés.
- Build en casa, no una plataforma comercial de roleplay/línea telefónica (ya evaluado y
  descartado antes de este baseline).
