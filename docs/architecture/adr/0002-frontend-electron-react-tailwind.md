# ADR-0002: Frontend — Electron + React + Tailwind

- **Status:** accepted
- **Date:** 2026-08-19 (reconstruido — decisión tomada antes de este baseline, sin stack obligatorio impuesto por la empresa)
- **Deciders:** autor original del proyecto, con mandato abierto del jefe de área ("sin stack obligatorio")

## Context and problem statement

El prototipo hoy es una CLI de terminal. El producto real necesita una interfaz gráfica de
escritorio para el supervisor: pantalla de llamada en vivo, escenarios, métricas, historial y
ajustes. ¿Con qué stack de UI se construye?

## Decision drivers

- El jefe de área no impuso un stack — la decisión quedó abierta al equipo.
- Necesidad de una app de escritorio instalable (no un sitio web) que corra en las PCs de los
  supervisores y se conecte al servidor LAN (ver [ADR-0004](./0004-topologia-de-despliegue.md)).
- El equipo ya tenía preferencia declarada por React/Tailwind antes de esta sesión.

## Considered options

1. Electron + React + Tailwind
2. Aplicación nativa (WPF/.NET o similar, dado que el entorno de desarrollo es Windows)
3. App web servida desde el servidor LAN, sin empaquetado de escritorio

## Decision

Se mantiene Electron + React + Tailwind, tal como se propuso desde el inicio de la planeación —
ninguna de las alternativas ofrece una ventaja que justifique desviarse de una preferencia de
equipo ya declarada y sin restricción corporativa en contra.

## Consequences

**Positive**
- Reusa el conocimiento de React/Tailwind del equipo; no hay curva de aprendizaje de un stack
  nuevo.
- Empaquetable como instalador de escritorio (ver Distribution Plan en el design doc de
  origen).

**Negative**
- Electron implica un runtime de Chromium+Node empaquetado por cliente — huella de disco/RAM
  mayor que una app nativa liviana.
- Ningún tipo compartido entre el cliente (TypeScript) y el servidor (Python) — el contrato del
  WebSocket debe mantenerse sincronizado manualmente entre ambos lados.

**Risks**
- Si el spike de latencia (Gate 0 del roadmap) muestra que el pipeline de audio necesita
  procesamiento nativo de bajo nivel en el cliente, Electron podría no ser suficiente sin un
  módulo nativo adicional — ver TODOS.md.

## Options not chosen

- **Aplicación nativa (.NET/WPF)**: mejor rendimiento y huella más chica, pero el equipo no
  tiene esa preferencia declarada y significaría empezar de cero sin reusar conocimiento
  existente.
- **App web sin empaquetado**: más simple de desplegar (sin instalador), pero pierde el control
  de acceso a hardware de audio nativo que un cliente de escritorio ofrece más directamente, y
  no encaja con la topología de "cliente liviano instalado" que ya se decidió en ADR-0004.
