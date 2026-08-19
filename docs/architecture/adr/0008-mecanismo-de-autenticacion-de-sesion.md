# ADR-0008: Mecanismo de autenticación de sesión — token propio por supervisor

- **Status:** accepted — confirmado por el usuario el 2026-08-19 (ver
  [TODO-02](../TODOS.md#todo-02)). Esta aceptación cubre el *mecanismo* de auth, no el gate
  completo de [AGENTS.md](../../../AGENTS.md) regla 5: ese gate también exige WSS/TLS
  implementado (todavía no) antes de fusionar código de servidor real.
- **Date:** 2026-08-19
- **Deciders:** usuario. La pregunta de si existe además un SSO corporativo real (TODO-02)
  sigue abierta — este ADR no depende de esa respuesta, ver Options not chosen.

## Context and problem statement

El servidor WebSocket en la LAN necesita autenticar supervisores y aislar la sesión de audio de
cada conexión ([NFR-04](../nfr.md#nfr-04)), sobre WSS/TLS ([NFR-05](../nfr.md#nfr-05)) — es un
gate de seguridad explícito para fusionar código de servidor, no una mejora posterior. TODO-02
deja abierta la pregunta de si hay un directorio corporativo (SSO/LDAP/AD) existente para
integrar. **No se confirmó esa integración en este baseline** — este ADR propone un mecanismo
propio mínimo que no depende de la respuesta a esa pregunta, para no bloquear Fase 1 en una
decisión organizacional pendiente, dejando explícito el camino de migración si luego aparece un
SSO real.

## Decision drivers

- Gate de seguridad no negociable (ver AGENTS.md regla 5) — hace falta algo aceptado antes de
  cualquier servidor real, no una promesa de resolverlo después.
- [NFR-11](../nfr.md#nfr-11) — 1 usuario a la vez, una sola ubicación: no hace falta un sistema
  de identidad multi-tenant, solo distinguir "este supervisor, esta sesión."
- Sin dueño operativo nombrado para el mecanismo de auth todavía ([TODO-02](../TODOS.md#todo-02))
  — cualquier opción que dependa de un directorio corporativo existente no se puede confirmar
  hoy porque no hay dueño que confirme si ese directorio existe o cómo integrarlo.

## Considered options

1. **Integración con SSO corporativo** (LDAP/AD/OIDC) — requiere confirmar que existe y quién
   lo administra.
2. **Token de sesión propio**: el supervisor se identifica una vez (usuario/contraseña propios
   del sistema, sin directorio externo), el servidor emite un token de sesión firmado con scope
   a esa conexión de audio específica.
3. **Sin auth, restringido solo por estar en la LAN interna** — confiar en el perímetro de red.

## Decision

Se elige la opción 2 — token de sesión propio, emitido por el servidor al autenticar
(usuario/contraseña gestionados por la propia app, hasheados, sin directorio externo), con
scope a una sola conexión de audio (una conexión no puede apuntar a la sesión de otra, según
exige NFR-04), transmitido solo sobre WSS/TLS (NFR-05). La opción 1 queda como migración futura
explícita si TODO-02 se resuelve confirmando que existe un SSO corporativo con dueño — este ADR
no la descarta, la trata como no confirmable hoy. La opción 3 se descarta: NFR-04/NFR-05 son
gates explícitos, no opcionales, y "está en la LAN" no es autenticación por supervisor ni aísla
sesiones entre sí.

## Consequences

**Positive**
- No depende de que TODO-02 se resuelva para poder avanzar con el rewrite de Fase 1 — desbloquea
  el trabajo técnico sin esperar una respuesta organizacional.
- Cumple el gate de NFR-04/NFR-05 con la superficie más chica posible (sin integrar un sistema
  externo todavía).
- Camino de migración a SSO real queda explícito, no es una puerta cerrada.

**Negative**
- Un sistema de credenciales propio es una superficie de seguridad nueva que mantener
  (hasheo de contraseñas, rotación, recuperación de acceso) — si ya existe un SSO corporativo,
  esto es trabajo duplicado que se descarta cuando se confirme.
- Sigue sin dueño operativo nombrado para administrar esas credenciales — esto no resuelve
  [TODO-02](../TODOS.md#todo-02)/[TODO-03](../TODOS.md#todo-03), solo evita que bloqueen el
  código.

**Risks**
- El gate de AGENTS.md regla 5 sigue exigiendo WSS/TLS implementado además de este mecanismo —
  aceptar este ADR habilita construir el adaptador de auth, no todavía fusionar el servidor
  completo contra la LAN real.
- Si aparece un SSO corporativo después de construir esto, la migración toca el adaptador de
  auth (detrás de su puerto, ver ADR-0006) pero no debería tocar el dominio — validar eso cuando
  ocurra, no asumirlo.

## Options not chosen

- **SSO corporativo (opción 1)**: la opción correcta si existe un directorio ya operado por
  IT — pero no confirmable hoy sin dueño nombrado (TODO-02). Revisitar apenas haya respuesta.
- **Solo perímetro de LAN (opción 3)**: viola NFR-04/NFR-05 directamente — no es una opción
  válida para Fase 1 según las reglas ya aceptadas en AGENTS.md.
