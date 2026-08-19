# Diagramas C4 — voice-agent

Los diagramas viven una sola vez, en [`arc42.md`](../arc42.md) (secciones 3, 5 y 7) — este
índice enlaza a cada nivel en vez de duplicar el diagrama, para que no haya dos fuentes de
verdad que puedan desincronizarse.

| Nivel C4 | Qué muestra | Fuente |
|---|---|---|
| **1 — Contexto** | Actores humanos (supervisor, jefe de área, IT/seguridad) y el único sistema externo (Claude API). | [arc42.md §3](../arc42.md#3-contexto-del-sistema) |
| **2 — Contenedores** | Cliente Electron/React vs. servidor LAN, y cómo se comunican (WSS/TLS, HTTPS a Claude). | [arc42.md §5](../arc42.md#5-vista-de-bloques-de-construcción) (mitad superior del diagrama) |
| **3 — Componentes (servidor)** | Dentro del servidor: gateway WebSocket, turn state machine, los 3 dominios (escenarios/métricas/historial), y los adaptadores hacia STT/TTS/LLM/persistencia. | [arc42.md §5](../arc42.md#5-vista-de-bloques-de-construcción) (mitad inferior del diagrama) |
| **Despliegue** | Topología física: PCs de supervisores + servidor RTX en la LAN del concesionario, Claude API en la nube. | [arc42.md §7](../arc42.md#7-vista-de-despliegue) |

No hay nivel 4 (Código) — el hexagonal de [ADR-0006](../adr/0006-arquitectura-hexagonal.md) ya
documenta la regla de dependencia (dominio nunca importa infraestructura); un diagrama de
código a este tamaño de proyecto sería ceremonia sin lector.
