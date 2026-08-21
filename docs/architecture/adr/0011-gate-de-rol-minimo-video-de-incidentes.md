# ADR-0011: Gate de rol mínimo antes de exponer video de incidentes reales

- **Status:** accepted — resuelto en la misma sesión de implementación de
  [escenarios-de-video.md](../../designs/escenarios-de-video.md) (TODO-16 acotado a video),
  sin bloquear en espera de diseñar el RBAC completo, según instrucción explícita del usuario.
- **Date:** 2026-08-21
- **Deciders:** implementación directa (Claude Code), sobre un hallazgo confirmado
  independientemente por CEO y Eng en `/autoplan` (hallazgo 4.2 de la revisión de ingeniería).

## Context and problem statement

TODO-16 documenta que este repo no tiene RBAC: cualquier sesión autenticada puede leer/escribir
`/incidents`, pensado conceptualmente para managers/RRHH. Mientras esa superficie era solo texto
(notas de post-mortem), el repo trató esa brecha como tolerable y diferible. La propuesta de
escenarios de video adjunta **video crudo de un robo real** al mismo flujo de incidentes al
promoverlos (paso 5 del roadmap de implementación) — un orden de exposición distinto (datos
biométricos de terceros, no solo texto). Diseñar el RBAC completo (roles, quién administra
membresía, SSO) es su propio trabajo, no algo para improvisar dentro de esta feature — pero
tampoco se puede exponer video real de incidentes sin ningún gate, dado que dos voces
independientes lo marcaron como bloqueante.

## Decision drivers

- No diseñar el RBAC completo ahora (TODO-16 sigue abierto para eso) — resolver solo lo que esta
  feature específica necesita: quién puede *ver* video de un incidente real.
- Reusar el patrón de auth ya aceptado en este repo (ADR-0008: una passphrase compartida por tipo
  de acceso, sin directorio externo) en vez de inventar un sistema de roles nuevo sin evidencia
  de que se necesite algo más granular todavía.
- NFR-11 (concurrencia=1, una sola ubicación): no hace falta un sistema de roles multi-tenant,
  solo distinguir "quien reporta un incidente" de "quien puede ver el video crudo de un
  incidente."

## Considered options

1. **Segunda passphrase de manager** (`MANAGER_PASSPHRASE`, env var nueva), mismo mecanismo que
   `SUPERVISOR_PASSPHRASE` (ADR-0008) — `login` acepta cualquiera de las dos y el token de sesión
   lleva un claim `role: "supervisor" | "manager"`; las rutas de video de incidentes exigen
   `role == "manager"`.
2. **RBAC completo** (tabla de roles, asignación por supervisor_id, posible integración SSO) —
   correcto a largo plazo, pero es exactamente el trabajo que TODO-16 ya señala como pendiente de
   diseño propio, no algo para decidir sin ese análisis.
3. **Sin gate — cualquier sesión autenticada ve el video** — es el status quo que ambas voces de
   revisión marcaron como bloqueante para este caso específico.

## Decision

Se elige la opción 1. `SessionTokenClaims` gana un campo `role: str = "supervisor"`;
`server_main.py` lee una nueva env var opcional `MANAGER_PASSPHRASE` (si no está seteada, no
existe ningún login de manager posible todavía — falla cerrado, no abierto: sin esa env var,
ninguna ruta de manager es alcanzable); `POST /auth/login` compara la passphrase recibida contra
ambas y asigna el rol correspondiente.

**Alcance exacto del gate** (nota de implementación, más angosto que la primera redacción de
este ADR): no existe un campo de video en `IncidentOutcome` — el video de un incidente real se
adjunta recién al promoverlo a escenario, como una referencia de archivo colocado manualmente
(mismo recorte de alcance que el resto de esta feature, ver escenarios-de-video.md). Por lo
tanto el gate se aplica puntualmente: `POST /incidents/{id}/promote-to-scenario` **solo cuando el
request incluye un video adjunto** exige `role == "manager"` (`403` si no); promover sin video
sigue funcionando exactamente igual que antes de este ADR, sin chequeo de rol nuevo — el resto de
`/incidents` (texto, CRUD) tampoco cambia, sigue siendo la brecha ya conocida y aceptada de
TODO-16, no ampliada ni reducida por este ADR.

La opción 2 se rechaza *para este ADR específicamente* — no porque esté mal, sino porque
diseñarla requiere las preguntas que TODO-16 ya nombra sin dueño (quién administra membresía,
si hay SSO real) y esta feature no debe esperar esas respuestas para tener un gate mínimo.
La opción 3 se rechaza: es el hallazgo de seguridad que este ADR existe para cerrar.

## Consequences

**Positive**
- Cierra el hallazgo crítico de la revisión de ingeniería (4.2) sin inflar el alcance de esta
  feature al tamaño de un sistema de roles completo.
- Reusa exactamente el mecanismo de auth ya aceptado (ADR-0008) — cero superficie de seguridad
  nueva más allá de una segunda passphrase y un claim adicional.
- Falla cerrado: sin `MANAGER_PASSPHRASE` configurada, no hay manera de autenticarse como manager
  — un despliegue que no configuró esto explícitamente no expone video de incidentes a nadie.

**Negative**
- Una passphrase compartida de manager es tan débil como la de supervisor ya lo es (ADR-0008 ya
  aceptó ese trade-off para el mecanismo general) — no es un sistema de identidad individual por
  manager, solo una distinción binaria de rol.
- No resuelve TODO-16 para el resto de `/incidents` (texto) ni para el editor de escenarios — ese
  alcance más amplio sigue exactamente como estaba, a propósito.

**Risks**
- Si en el futuro se necesita saber *cuál* manager vio o promovió un incidente específico (no solo
  "algún manager"), este mecanismo no lo distingue — mismo límite que ya tiene el mecanismo de
  supervisor de ADR-0008, heredado a propósito, no un descuido nuevo.

## Options not chosen

- **RBAC completo (opción 2)**: la opción correcta si el producto crece más allá de este alcance
  — TODO-16 sigue abierto exactamente para esa decisión más grande, este ADR no la reemplaza.
- **Sin gate (opción 3)**: descartada, es el hallazgo de seguridad que motivó este ADR.
