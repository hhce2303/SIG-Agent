# arc42 — voice-agent

Archivo único (no 12 archivos separados) — proyecto de un solo equipo chico, se lee de corrido.
Cada sección enlaza a su fuente de verdad en vez de duplicar contenido; donde no hay fuente
todavía, queda marcado `[GAP — POR ESCRIBIR]` en vez de quedar en silencio.

---

## 1. Introducción y objetivos

Ver [`GOALS.md`](./GOALS.md) — fuente completa. Resumen: entrenar supervisores de
concesionario a reportar incidentes a la policía mediante llamadas de práctica en tiempo real
contra un dispatcher simulado por IA, auditadas después con métricas objetivas.

## 2. Restricciones de arquitectura

- Una sola ubicación/concesionario, 1 sesión concurrente (ver [NFR-11](./nfr.md#nfr-11)).
- El LLM siempre depende de conectividad a internet (Claude API) — ver
  [ADR-0003](./adr/0003-proveedor-llm-claude-api.md).
- Sin stack obligatorio impuesto por la empresa, salvo las decisiones ya tomadas en
  [ADR-0001](./adr/0001-lenguaje-backend-python.md) y
  [ADR-0002](./adr/0002-frontend-electron-react-tailwind.md).
- Sin restricción regulatoria de grabación de voz confirmada todavía (ver
  [TODO-05](./TODOS.md#todo-05)) — no asumir que no aplica ninguna.

## 3. Contexto del sistema

**Actores humanos:**

| Actor | Interacción |
|---|---|
| Supervisor (trainee) | Usa el cliente Electron para sostener una llamada de práctica y revisar su historial/métricas. |
| Jefe de área (sponsor) | No interactúa con el sistema en runtime; consume el resultado (supervisores mejor entrenados) y aprueba alcance/presupuesto. |
| IT / Seguridad | Administra el servidor LAN (dueño operativo, ver [TODO-03](./TODOS.md#todo-03)) y el mecanismo de auth. |
| Segundo ingeniero (a nombrar) | Mantiene y extiende el código — ver [TODO-06](./TODOS.md#todo-06). |

**Sistemas externos:**

| Sistema | Protocolo | Quién lo posee |
|---|---|---|
| Claude API (Anthropic) | HTTPS, API de mensajes | Anthropic — servicio externo, fuera del control del equipo. |

```mermaid
flowchart LR
    S["Supervisor"] -->|"habla / escucha"| C["Cliente Electron"]
    C <-->|"WebSocket + WSS/TLS"| SRV["Servidor LAN (RTX)"]
    SRV -->|"HTTPS"| CLAUDE["Claude API (Anthropic)"]
    IT["IT / Seguridad"] -.->|"administra"| SRV
    SUP["Jefe de área"] -.->|"consume resultado, no runtime"| S
```

## 4. Estrategia de solución

Síntesis de los 6 ADRs vigentes:

- Backend en Python ([ADR-0001](./adr/0001-lenguaje-backend-python.md)), cliente Electron +
  React + Tailwind ([ADR-0002](./adr/0002-frontend-electron-react-tailwind.md)).
- LLM en la nube vía Claude API, nunca local ([ADR-0003](./adr/0003-proveedor-llm-claude-api.md)).
- Servidor centralizado en la LAN con GPU RTX, no un ejecutable por PC
  ([ADR-0004](./adr/0004-topologia-de-despliegue.md)).
- Detección automática de voz por turnos, sin interrupciones (barge-in) todavía
  ([ADR-0005](./adr/0005-audio-en-vivo-vad-sin-barge-in.md)).
- Backend organizado en hexagonal (puertos/adaptadores), sin el aparato táctico completo de DDD
  ([ADR-0006](./adr/0006-arquitectura-hexagonal.md)).

## 5. Vista de bloques de construcción

```mermaid
flowchart TB
    subgraph Cliente["Cliente Electron/React (PC del supervisor)"]
        UI_CALL["Pantalla de llamada\n(indicador de turno)"]
        UI_SCEN["Editor de escenarios"]
        UI_MET["Métricas / Historial"]
        UI_SET["Ajustes"]
    end

    subgraph Servidor["Servidor LAN (RTX) — hexagonal"]
        GW["Gateway WebSocket\n(estado de turno)"]
        subgraph Dominio["Núcleo de dominio"]
            TURN["Turn state machine"]
            SCEN_D["Dominio: Escenarios"]
            MET_D["Dominio: Métricas"]
            HIST_D["Dominio: Historial"]
        end
        subgraph Adaptadores["Adaptadores (puertos hacia infraestructura)"]
            STT["Adaptador STT\n(faster-whisper)"]
            TTS["Adaptador TTS\n(Kokoro)"]
            LLM_A["Adaptador LLM\n(Claude API)"]
            DB["Adaptador de persistencia\n(TODO-01, sin elegir)"]
        end
    end

    CLAUDE_EXT["Claude API (externo)"]

    UI_CALL <--> GW
    UI_SCEN <--> GW
    UI_MET <--> GW
    UI_SET <--> GW
    GW --> TURN
    TURN --> STT
    TURN --> TTS
    TURN --> LLM_A
    SCEN_D --> DB
    MET_D --> DB
    HIST_D --> DB
    LLM_A --> CLAUDE_EXT
```

Los adaptadores STT/TTS/LLM ya existen como clases en el prototipo
(`WhisperSTT`, `KokoroTTS`, `ClaudeDispatcher`) — ver
[ADR-0006](./adr/0006-arquitectura-hexagonal.md) para qué sobrevive tal cual y qué se reescribe.

## 6. Vista de tiempo de ejecución

Cinco escenarios concretos — el camino feliz, el de manejo de error más delicado, el de mayor
duración, y los dos que cruzan más límites de componentes.

**6.1 — Camino feliz: un turno completo**

```mermaid
sequenceDiagram
    participant Sup as Supervisor
    participant Cli as Cliente
    participant GW as Gateway/Turn SM
    participant STT
    participant LLM as Claude API
    participant TTS

    Sup->>Cli: habla
    Cli->>GW: audio stream
    GW->>GW: VAD detecta fin de turno
    GW->>STT: audio del turno
    STT-->>GW: texto + confianza
    GW->>LLM: turno + contexto de escenario
    LLM-->>GW: respuesta del dispatcher
    GW->>TTS: texto de respuesta
    TTS-->>GW: audio sintetizado
    GW->>Cli: audio + estado "dispatcher-hablando"
    Cli->>Sup: reproduce respuesta
```

**6.2 — Error de Claude API a medio turno (ver [NFR-02](./nfr.md#nfr-02))**

```mermaid
sequenceDiagram
    participant GW as Gateway/Turn SM
    participant LLM as Claude API

    GW->>LLM: turno + contexto
    LLM--xGW: timeout / rate-limit
    GW->>GW: retry acotado
    alt recupera en el retry
        LLM-->>GW: respuesta
    else sigue fallando
        GW->>GW: entra a estado "recuperación de error"
        GW-->>Cli: dispatcher dice "¿puede repetir eso?"
    end
```

**6.3 — Corte falso de VAD**

```mermaid
sequenceDiagram
    participant Sup as Supervisor
    participant GW as Gateway/Turn SM

    Sup->>GW: habla, pausa (pensando la placa)
    GW->>GW: VAD corta el turno de forma prematura
    GW->>GW: entra a "recuperación de corte falso"
    Note over GW: no se dispara la respuesta del<br/>dispatcher todavía
    Sup->>GW: continúa hablando
    GW->>GW: retoma el mismo turno
```

**6.4 — Caída de red LAN a medio turno**

```mermaid
sequenceDiagram
    participant Cli as Cliente
    participant GW as Gateway

    Cli->>GW: audio stream
    Note over Cli,GW: conexión se degrada / cae
    GW--xCli: pérdida de frames
    Cli->>Cli: estado "red-degradada" visible
    alt reconecta a tiempo
        Cli->>GW: reconecta, retoma sesión
    else no reconecta
        Cli->>Cli: pantalla "llamada terminada por conexión"
    end
```

**6.5 — Sesión completa, de mayor duración**

Encadena 6.1 N veces hasta que el supervisor termina o aborta la llamada, seguido de la
transición de decompresión y la generación del score (ver
[TODO-10](./TODOS.md#todo-10), fórmula pendiente).

## 7. Vista de despliegue

```mermaid
flowchart TB
    subgraph Concesionario["Red interna del concesionario (una sola ubicación)"]
        PC1["PC supervisor 1\n(Cliente Electron)"]
        PC2["PC supervisor N\n(Cliente Electron)"]
        RTX["Servidor LAN\nGPU RTX — FastAPI/WebSocket\nSTT + TTS + turn state machine"]
    end
    CLOUD["Claude API\n(Anthropic, cloud)"]

    PC1 <-->|"WSS/TLS"| RTX
    PC2 <-->|"WSS/TLS"| RTX
    RTX <-->|"HTTPS"| CLOUD
```

Concurrencia de diseño = 1 sesión a la vez ([NFR-11](./nfr.md#nfr-11)) — el diagrama muestra
múltiples PCs posibles, no sesiones simultáneas.

## 8. Conceptos transversales

- **Manejo de error**: ver [NFR-02](./nfr.md#nfr-02) — vive en los adaptadores, nunca en el
  dominio (regla de [ADR-0006](./adr/0006-arquitectura-hexagonal.md)).
- **Logging/observabilidad**: ver [NFR-08](./nfr.md#nfr-08).
- **Seguridad**: ver [NFR-04](./nfr.md#nfr-04), [NFR-05](./nfr.md#nfr-05).
- **Puertos y adaptadores**: regla no negociable en [CONTRIBUTING.md](../../CONTRIBUTING.md).

## 9. Decisiones de arquitectura

| ADR | Título | Estado |
|---|---|---|
| [0001](./adr/0001-lenguaje-backend-python.md) | Lenguaje/runtime del backend — Python | accepted |
| [0002](./adr/0002-frontend-electron-react-tailwind.md) | Frontend — Electron + React + Tailwind | accepted |
| [0003](./adr/0003-proveedor-llm-claude-api.md) | Proveedor de LLM — Claude API | accepted |
| [0004](./adr/0004-topologia-de-despliegue.md) | Topología de despliegue — servidor LAN + RTX | accepted — condicionado a spike (Gate 0) |
| [0005](./adr/0005-audio-en-vivo-vad-sin-barge-in.md) | Audio en vivo — VAD por turnos, sin barge-in | accepted |
| [0006](./adr/0006-arquitectura-hexagonal.md) | Estilo arquitectónico — hexagonal, sin DDD táctico | accepted |

## 10. Requisitos de calidad

Ver [`nfr.md`](./nfr.md) — fuente completa, 12 NFRs con ID estable. Los tres más críticos para
Fase 1: [NFR-01](./nfr.md#nfr-01) (latencia), [NFR-02](./nfr.md#nfr-02) (recuperación en
banda), [NFR-06](./nfr.md#nfr-06) (privacidad del historial).

## 11. Riesgos y deuda técnica

Ver [`TODOS.md`](./TODOS.md) — fuente completa, 14 ítems con ID estable. El mayor riesgo activo
hoy: [TODO-08](./TODOS.md#todo-08), del cual dependen directamente ADR-0004 y ADR-0005.

## 12. Glosario

Ver [`glossary.md`](./glossary.md) — fuente completa.
