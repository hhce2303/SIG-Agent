# TODOS — decisiones pendientes y riesgos conocidos, voice-agent

Estado: `PENDING` (no iniciado) / `IN PROGRESS` / `[RESOLVED vX.X]`. IDs estables, nunca se
reordenan ni se borran — un TODO resuelto queda marcado, no desaparece.

## Bloqueantes de Fase 1

### TODO-01
**Motor de persistencia.** Estado: IN PROGRESS.
No existe hoy ninguna capa de storage (escenarios, métricas, historial son greenfield — ver
[ADR-0006](./adr/0006-arquitectura-hexagonal.md)). Elegir motor (SQLite/Postgres/otro) es un
ADR pendiente de escribir, no un detalle de implementación. **Actualización 2026-08-19:**
[ADR-0007](./adr/0007-motor-de-persistencia.md) (SQLite embebido) — `accepted` por el usuario.
Queda IN PROGRESS (no RESOLVED) hasta que el adaptador esté implementado y en uso por el
servidor real, no solo decidido.

### TODO-02
**Mecanismo de autenticación de supervisores.** Estado: IN PROGRESS.
¿Hay un directorio/SSO corporativo existente para integrar, o se necesita uno propio? Sin
dueño nombrado. Relacionado: [NFR-04](./nfr.md#nfr-04). Bloqueante antes de fusionar código de
servidor según la revisión de ingeniería de `/autoplan`. **Actualización 2026-08-19:**
[ADR-0008](./adr/0008-mecanismo-de-autenticacion-de-sesion.md) (token de sesión propio, sin
asumir SSO corporativo) — `accepted` por el usuario. Sigue IN PROGRESS: falta implementar y
usar el adaptador en el servidor real, y la pregunta de si existe además un SSO corporativo
real sigue sin dueño y sigue abierta (no bloquea este mecanismo, ver ADR-0008).

### TODO-03
**Dueño operativo de la caja RTX.** Estado: PENDING.
¿IT o el equipo del sponsor? Sin nombre asignado, este tipo de pieza (servidor + auth en la red
interna) suele estancarse en revisión de seguridad por meses.

### TODO-04
**Política de retención y visibilidad del historial.** Estado: PENDING.
¿Cuánto tiempo se retienen audio/transcripts? ¿Quién puede ver el historial de quién — el
propio supervisor, su jefe, RRHH? Ver [NFR-06](./nfr.md#nfr-06). Sin esto, los supervisores no
practican honestamente.

### TODO-05
**Cumplimiento regulatorio de grabación de voz.** Estado: PENDING.
No se confirmó ninguna restricción legal conocida (leyes estatales de consentimiento para
grabar empleados, política de monitoreo de RRHH, residencia de datos) durante el baseline de
arquitectura. Ver [NFR-07](./nfr.md#nfr-07) — se documenta explícitamente como pendiente, no se
asume que "no aplica".

### TODO-06
**Segundo ingeniero/revisor.** Estado: PENDING.
Bus factor de 1 persona en todo el pipeline STT/LLM/TTS, sin tests. Nombrar antes de Fase 1 —
debería empezar por el harness de tests ([NFR-10](./nfr.md#nfr-10)), antes de tocar el rewrite.

### TODO-07
**Presupuesto de capital para la GPU RTX.** Estado: PENDING.
El pedido original solo menciona tiempo asignado por el jefe de área, no capex de hardware.
Confirmar por separado antes de programar el spike de Gate 0.

## Condiciona decisiones ya tomadas

### TODO-08
**Resultado del spike de Gate 0.** Estado: PENDING.
Latencia end-to-end (incluyendo round-trip a Claude), prueba de red real con dos máquinas, y
user-test barato de VAD vs. push-to-talk con 2-3 supervisores. Condiciona directamente
[ADR-0004](./adr/0004-topologia-de-despliegue.md) y [ADR-0005](./adr/0005-audio-en-vivo-vad-sin-barge-in.md).

### TODO-09
**Clasificación de causa raíz del incidente documentado.** Estado: PENDING.
¿Pánico/habla bajo presión, falta de datos a la mano, no saber a quién llamar, o
desconocimiento de protocolo? Informa qué debe entrenar realmente el simulador — hacerlo antes
de cerrar el alcance de Fase 1.

### TODO-10
**Fórmula de ponderado/score de métricas.** Estado: PENDING.
Peso relativo de tiempo-hasta-dato-crítico, completitud, claridad/muletillas, y tiempo total.
Bloquea el diseño de UI de la pantalla de métricas (Fase 2).

### TODO-11
**Formato del editor de escenarios.** Estado: PENDING.
Campos estructurados guiados vs. texto libre (tipo el `SCENARIO` string actual). Determina si
la pantalla es un formulario validado o un editor de texto/plantillas — son problemas de UI
distintos. Bloquea el diseño de UI del editor (Fase 2).

## Contingencias (se activan solo si su condición ocurre)

### TODO-12
**Streaming de respuesta de Claude.** Estado: PENDING (contingente a TODO-08).
Si el spike de Gate 0 muestra que el round-trip a Claude por sí solo rompe el presupuesto de
[NFR-01](./nfr.md#nfr-01), tratar la integración de streaming (tokens de Claude → síntesis
incremental de TTS) como workstream propio de Fase 2, no como nota al pie. Ver
[ADR-0003](./adr/0003-proveedor-llm-claude-api.md), sección Risks.

### TODO-13
**Revisitar ADR-0004 si la operación crece a más de una ubicación.** Estado: PENDING
(contingente a expansión de negocio).
La topología de servidor LAN + RTX se decidió asumiendo una sola ubicación. Si se agregan
sitios, replicar servidor + dueño + auth por sitio puede invertir la recomendación hacia el
ejecutable standalone (Approach A de ADR-0004).

### TODO-14
**Revisitar ADR-0001 si se necesita alta concurrencia.** Estado: PENDING (contingente a cambio
de escala).
Python fue elegido asumiendo concurrencia=1 ([NFR-11](./nfr.md#nfr-11)). Si el proyecto
creciera a necesitar servir muchas sesiones simultáneas, esta decisión debería revisitarse.
